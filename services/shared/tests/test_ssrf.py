"""SSRF guard tests — the full hostile matrix plus legitimate-fetch proof.

These exercise the URL/IP validation core (``resolve_and_validate`` /
``SsrfPolicy.is_ip_blocked``) directly, the DNS-resolution path (a hostname
whose A record is a private IP must be rejected), redirect re-validation, and
the integration into the source adapters (a malicious ``adapter_config`` URL is
rejected before any fetch fires).

DNS is faked via monkeypatching ``socket.getaddrinfo`` so the suite needs no
network.  The "legitimate public source still works" proof uses a borrowed
``httpx.MockTransport`` client (the adapters trust a borrowed client but still
pre-validate the configured public URL through the guard).
"""

from __future__ import annotations

import socket
from typing import Any

import pytest
from intercal_shared.ssrf import (
    DEFAULT_POLICY,
    ResolvedTarget,
    SsrfError,
    SsrfPolicy,
    resolve_and_validate,
)

# ──────────────────────────────────────────────────────────────────────────────
# DNS faking helper
# ──────────────────────────────────────────────────────────────────────────────


def _fake_getaddrinfo(mapping: dict[str, list[str]]) -> Any:
    """Build a getaddrinfo replacement resolving hosts per *mapping*.

    *mapping* maps hostname -> list of IP strings (v4 and/or v6).  Unlisted
    hosts raise ``socket.gaierror`` (NXDOMAIN-like).
    """

    def _impl(host: str, port: int, *args: Any, **kwargs: Any) -> list[Any]:
        ips = mapping.get(host)
        if ips is None:
            raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")
        out: list[Any] = []
        for ip in ips:
            is_v6 = ":" in ip
            family = socket.AF_INET6 if is_v6 else socket.AF_INET
            sockaddr: tuple[Any, ...] = (ip, port, 0, 0) if is_v6 else (ip, port)
            out.append((family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr))
        return out

    return _impl


# ──────────────────────────────────────────────────────────────────────────────
# Scheme allowlist
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/x",
        "gopher://example.com:70/_",
        "data:text/plain,hi",
        "ldap://example.com",
    ],
)
def test_disallowed_schemes_rejected(url: str) -> None:
    with pytest.raises(SsrfError) as exc:
        resolve_and_validate(url)
    assert exc.value.reason == "scheme"


def test_missing_host_rejected() -> None:
    with pytest.raises(SsrfError) as exc:
        resolve_and_validate("http:///nohost")
    assert exc.value.reason == "no_host"


# ──────────────────────────────────────────────────────────────────────────────
# Hostile IP literals (incl. alternate encodings)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        # Loopback in canonical and alternate IPv4 encodings.
        ("http://127.0.0.1/", "loopback"),
        ("http://localhost/", "loopback"),  # resolves to 127.0.0.1 via fake DNS
        ("http://2130706433/", "loopback"),  # decimal 127.0.0.1
        ("http://0x7f000001/", "loopback"),  # hex 127.0.0.1
        ("http://0177.0.0.1/", "loopback"),  # octal 127.0.0.1
        # Unspecified / "all interfaces".
        ("http://0.0.0.0/", "unspecified"),
        # Cloud instance metadata (AWS/GCP/Azure share this address).
        ("http://169.254.169.254/latest/meta-data/", "cloud_metadata"),
        # Other link-local.
        ("http://169.254.1.1/", "link_local"),
        # RFC1918 private ranges.
        ("http://10.0.0.5/", "private"),
        ("http://172.16.0.1/", "private"),
        ("http://192.168.1.1/", "private"),
        # Multicast.
        ("http://224.0.0.1/", "multicast"),
        # IPv6 loopback, link-local, ULA, unspecified.
        ("http://[::1]/", "loopback"),
        ("http://[fe80::1]/", "link_local"),
        ("http://[fc00::1]/", "private"),
        ("http://[fd00::1]/", "private"),
        ("http://[::]/", "unspecified"),
        # IPv6 that embeds a private IPv4 (mapped / 6to4) must be unwrapped.
        ("http://[::ffff:10.0.0.1]/", "private"),
        ("http://[::ffff:169.254.169.254]/", "cloud_metadata"),
    ],
)
def test_hostile_ip_literals_rejected(
    url: str, reason: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo({"localhost": ["127.0.0.1"]}))
    with pytest.raises(SsrfError) as exc:
        resolve_and_validate(url)
    assert exc.value.reason == reason, f"{url} -> expected {reason}, got {exc.value.reason}"


# ──────────────────────────────────────────────────────────────────────────────
# DNS rebinding: a public hostname whose A/AAAA record is private must be blocked
# ──────────────────────────────────────────────────────────────────────────────


def test_dns_name_resolving_to_private_ip_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket, "getaddrinfo", _fake_getaddrinfo({"evil.example.com": ["10.1.2.3"]})
    )
    with pytest.raises(SsrfError) as exc:
        resolve_and_validate("https://evil.example.com/path")
    assert exc.value.reason == "private"


def test_dns_name_resolving_to_metadata_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket, "getaddrinfo", _fake_getaddrinfo({"rebind.example.com": ["169.254.169.254"]})
    )
    with pytest.raises(SsrfError) as exc:
        resolve_and_validate("http://rebind.example.com/")
    assert exc.value.reason == "cloud_metadata"


def test_dns_name_with_mixed_records_blocks_if_any_private(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If a host returns one public and one private address, it must be blocked
    (an attacker could otherwise round-robin onto the private one)."""
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        _fake_getaddrinfo({"mixed.example.com": ["93.184.216.34", "127.0.0.1"]}),
    )
    with pytest.raises(SsrfError) as exc:
        resolve_and_validate("https://mixed.example.com/")
    assert exc.value.reason == "loopback"


def test_unresolvable_host_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo({}))
    with pytest.raises(SsrfError) as exc:
        resolve_and_validate("https://nx.example.com/")
    assert exc.value.reason == "dns"


# ──────────────────────────────────────────────────────────────────────────────
# Legitimate public sources still pass
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("url", "ips"),
    [
        ("https://www.wikidata.org/w/api.php", ["208.80.154.224"]),
        ("https://api.github.com/repos/x/y/releases", ["140.82.112.6"]),
        (
            "https://en.wikipedia.org/api/rest_v1/page/summary",
            ["2606:2800:220:1:248:1893:25c8:1946"],
        ),
    ],
)
def test_public_urls_allowed(url: str, ips: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    from urllib.parse import urlsplit

    host = urlsplit(url).hostname or ""
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo({host: ips}))
    target = resolve_and_validate(url)
    assert isinstance(target, ResolvedTarget)
    assert target.host == host
    assert target.ip_addresses == tuple(ips)


def test_public_ipv6_literal_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    # A globally-routable IPv6 literal (Google public DNS over a fictional host).
    target = resolve_and_validate("https://[2606:2800:220:1:248:1893:25c8:1946]/")
    assert target.host == "2606:2800:220:1:248:1893:25c8:1946"


# ──────────────────────────────────────────────────────────────────────────────
# allow_private escape hatch (self-host only)
# ──────────────────────────────────────────────────────────────────────────────


def test_allow_private_policy_permits_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo({"localhost": ["127.0.0.1"]}))
    policy = SsrfPolicy(allow_private=True)
    target = resolve_and_validate("http://localhost:8080/", policy)
    assert target.host == "localhost"


# ──────────────────────────────────────────────────────────────────────────────
# Policy.is_ip_blocked direct unit coverage
# ──────────────────────────────────────────────────────────────────────────────


def test_default_policy_schemes() -> None:
    assert DEFAULT_POLICY.allowed_schemes == frozenset({"http", "https"})
    assert DEFAULT_POLICY.allow_private is False


# ──────────────────────────────────────────────────────────────────────────────
# Redirect re-validation (guarded_get)
# ──────────────────────────────────────────────────────────────────────────────


async def test_guarded_get_blocks_redirect_to_private_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A public URL that 302s to a private/metadata address must be blocked at
    the redirect hop, not followed."""
    import httpx
    from intercal_shared.ssrf import guarded_get

    # Public host resolves fine; the redirect target resolves to metadata.
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        _fake_getaddrinfo(
            {
                "public.example.com": ["93.184.216.34"],
                "internal.example.com": ["169.254.169.254"],
            }
        ),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        # The pinning transport rewrites the host to the validated IP, so match
        # on the path instead of the (now IP) host.
        return httpx.Response(302, headers={"location": "http://internal.example.com/steal"})

    # A borrowed MockTransport client bypasses the pinning transport; drive the
    # redirect logic directly. guarded_get re-validates the Location before the
    # next hop, which is where the block must fire.
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(SsrfError) as exc:
        await guarded_get(client, "http://public.example.com/start")
    await client.aclose()
    assert exc.value.reason == "cloud_metadata"


async def test_guarded_get_returns_non_redirect_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx
    from intercal_shared.ssrf import guarded_get

    monkeypatch.setattr(
        socket, "getaddrinfo", _fake_getaddrinfo({"public.example.com": ["93.184.216.34"]})
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    resp = await guarded_get(client, "http://public.example.com/x")
    await client.aclose()
    assert resp.status_code == 200


async def test_read_capped_rejects_oversized_body() -> None:
    import httpx
    from intercal_shared.ssrf import read_capped

    big = b"x" * 5000

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=big)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with client.stream("GET", "http://h/") as resp:
        with pytest.raises(SsrfError) as exc:
            await read_capped(resp, max_bytes=1000)
    await client.aclose()
    assert exc.value.reason == "too_large"


# ──────────────────────────────────────────────────────────────────────────────
# Guarded-client body-size cap (enforced by the pinning transport on EVERY
# response — not only when a caller remembers to use read_capped). These swap the
# transport's inner network transport for a MockTransport so no socket is opened.
# ──────────────────────────────────────────────────────────────────────────────


def _guarded_client_with_inner(handler: Any, policy: SsrfPolicy | None = None) -> Any:
    """Build a guarded client whose pinning transport delegates to *handler*.

    The pinning + validation logic still runs; only the final network hop is
    replaced by a MockTransport so the cap/Content-Length logic is exercised
    without a real socket.
    """
    import httpx
    from intercal_shared.ssrf import DEFAULT_POLICY, create_guarded_client

    client = create_guarded_client(policy or DEFAULT_POLICY)
    client._transport._inner = httpx.MockTransport(handler)  # type: ignore[attr-defined]
    return client


async def test_guarded_client_caps_oversized_streamed_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A body larger than max_bytes (with no/lying Content-Length) trips the cap
    on a buffered .aread()/.json()/.text read through a guarded client."""
    import httpx
    from intercal_shared.ssrf import SsrfPolicy

    monkeypatch.setattr(
        socket, "getaddrinfo", _fake_getaddrinfo({"public.example.com": ["93.184.216.34"]})
    )
    policy = SsrfPolicy(max_bytes=1000)

    def handler(request: httpx.Request) -> httpx.Response:
        # Stream chunks so total exceeds the cap; omit Content-Length so only the
        # streaming cap can catch it (defeats a lying/absent Content-Length).
        async def agen():  # type: ignore[no-untyped-def]
            for _ in range(5):
                yield b"x" * 400

        # An async-iterable body makes httpx emit a streaming (no Content-Length)
        # response, so the cap must catch it mid-stream.
        return httpx.Response(200, content=agen())

    client = _guarded_client_with_inner(handler, policy)
    with pytest.raises(SsrfError) as exc:
        await client.get("http://public.example.com/big")
    await client.aclose()
    assert exc.value.reason == "too_large"


async def test_guarded_client_rejects_oversized_content_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An over-cap Content-Length is rejected up front, before the body is read."""
    import httpx
    from intercal_shared.ssrf import SsrfPolicy

    monkeypatch.setattr(
        socket, "getaddrinfo", _fake_getaddrinfo({"public.example.com": ["93.184.216.34"]})
    )
    policy = SsrfPolicy(max_bytes=1000)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-length": "999999"}, content=b"x" * 10)

    client = _guarded_client_with_inner(handler, policy)
    with pytest.raises(SsrfError) as exc:
        await client.get("http://public.example.com/big")
    await client.aclose()
    assert exc.value.reason == "too_large"


async def test_guarded_client_allows_within_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """A body within the cap reads normally through a guarded client."""
    import httpx

    monkeypatch.setattr(
        socket, "getaddrinfo", _fake_getaddrinfo({"public.example.com": ["93.184.216.34"]})
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    client = _guarded_client_with_inner(handler)
    resp = await client.get("http://public.example.com/x")
    assert resp.json() == {"ok": True}
    await client.aclose()


async def test_guarded_client_blocks_private_at_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pinning transport itself validates: a host resolving to a private IP
    is rejected before the (mock) network hop — the guard is on the connect path,
    not only the pre-validate call."""
    import httpx

    monkeypatch.setattr(
        socket, "getaddrinfo", _fake_getaddrinfo({"rebind.example.com": ["10.0.0.7"]})
    )

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        raise AssertionError("network hop reached for a blocked host")

    client = _guarded_client_with_inner(handler)
    with pytest.raises(SsrfError) as exc:
        await client.get("http://rebind.example.com/")
    await client.aclose()
    assert exc.value.reason == "private"


# ──────────────────────────────────────────────────────────────────────────────
# Additional adversarial URL-shape vectors
# ──────────────────────────────────────────────────────────────────────────────


def test_userinfo_in_url_validates_real_host_not_userinfo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``http://expected.com@127.0.0.1/`` must validate the REAL host (127.0.0.1),
    not the userinfo (expected.com). urlsplit puts only the host in .hostname."""
    monkeypatch.setattr(
        socket, "getaddrinfo", _fake_getaddrinfo({"expected.com": ["93.184.216.34"]})
    )
    with pytest.raises(SsrfError) as exc:
        resolve_and_validate("http://expected.com@127.0.0.1/")
    assert exc.value.reason == "loopback"


def test_userinfo_with_public_host_uses_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """Userinfo present but the real host is public → validated on the host."""
    monkeypatch.setattr(
        socket, "getaddrinfo", _fake_getaddrinfo({"real.example.com": ["93.184.216.34"]})
    )
    target = resolve_and_validate("https://user:pass@real.example.com/path")
    assert target.host == "real.example.com"


def test_dns_resolving_to_ipv4_mapped_ipv6_metadata_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hostname whose AAAA record is an IPv4-mapped IPv6 wrapping the metadata
    address must be unwrapped and blocked."""
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        _fake_getaddrinfo({"sneaky.example.com": ["::ffff:169.254.169.254"]}),
    )
    with pytest.raises(SsrfError) as exc:
        resolve_and_validate("https://sneaky.example.com/")
    assert exc.value.reason == "cloud_metadata"


def test_overlong_octal_ipv4_canonicalised_and_blocked() -> None:
    """Octal-padded loopback (``0177.0000.0000.0001``) canonicalises to 127.0.0.1."""
    with pytest.raises(SsrfError) as exc:
        resolve_and_validate("http://0177.0000.0000.0001/")
    assert exc.value.reason == "loopback"


def test_short_form_ipv4_decimal_blocked() -> None:
    """Short-form ``127.1`` (libc expands to 127.0.0.1) is blocked."""
    with pytest.raises(SsrfError) as exc:
        resolve_and_validate("http://127.1/")
    assert exc.value.reason == "loopback"


def test_invalid_port_rejected() -> None:
    with pytest.raises(SsrfError) as exc:
        resolve_and_validate("http://example.com:notaport/")
    assert exc.value.reason == "port"


async def test_guarded_get_rejects_non_http_redirect_scheme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 302 Location with a non-http(s) scheme (file://) must be rejected at the
    redirect hop, not followed."""
    import httpx
    from intercal_shared.ssrf import guarded_get

    monkeypatch.setattr(
        socket, "getaddrinfo", _fake_getaddrinfo({"public.example.com": ["93.184.216.34"]})
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "file:///etc/passwd"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(SsrfError) as exc:
        await guarded_get(client, "http://public.example.com/start")
    await client.aclose()
    assert exc.value.reason == "scheme"


# ──────────────────────────────────────────────────────────────────────────────
# Adapter integration: malicious adapter_config URL is rejected before fetch
# ──────────────────────────────────────────────────────────────────────────────


async def test_wikidata_adapter_rejects_metadata_url(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx
    from intercal_shared.adapters.source_wikidata import WikidataChangesAdapter
    from intercal_shared.ports.source import SourceFetchError

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo({}))

    # Borrowed client so we reach the pre-validation (which fires regardless).
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    client = httpx.AsyncClient(transport=transport)
    adapter = WikidataChangesAdapter()
    with pytest.raises(SourceFetchError, match="SSRF"):
        async for _ in adapter.fetch(
            adapter_config={"wikidata_api_url": "http://169.254.169.254/latest/"},
            cursor_state=None,
            max_documents=5,
            http_client=client,
        ):
            pass
    await client.aclose()


async def test_github_adapter_rejects_private_url(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx
    from intercal_shared.adapters.source_github import GitHubReleasesAdapter
    from intercal_shared.ports.source import SourceFetchError

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo({}))

    transport = httpx.MockTransport(lambda r: httpx.Response(200, json=[]))
    client = httpx.AsyncClient(transport=transport)
    adapter = GitHubReleasesAdapter()
    with pytest.raises(SourceFetchError, match="SSRF"):
        async for _ in adapter.fetch(
            adapter_config={"repos": ["x/y"], "github_api_url": "http://10.0.0.1/"},
            cursor_state=None,
            max_documents=5,
            http_client=client,
        ):
            pass
    await client.aclose()


async def test_wikidata_adapter_allows_public_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard must not break legitimate ingestion: a public configured URL
    still fetches and yields documents."""
    import httpx
    from intercal_shared.adapters.source_wikidata import WikidataChangesAdapter
    from intercal_shared.ports.source import RawDocument

    monkeypatch.setattr(
        socket, "getaddrinfo", _fake_getaddrinfo({"www.wikidata.org": ["208.80.154.224"]})
    )

    api_response = {
        "query": {
            "recentchanges": [
                {
                    "rcid": 1,
                    "revid": 11,
                    "title": "Q1",
                    "ns": 0,
                    "type": "edit",
                    "timestamp": "2026-06-05T00:00:00Z",
                }
            ]
        }
    }
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=api_response))
    )
    adapter = WikidataChangesAdapter()
    docs: list[RawDocument] = []
    async for doc in adapter.fetch(
        adapter_config={"wikidata_api_url": "https://www.wikidata.org/w/api.php"},
        cursor_state=None,
        max_documents=5,
        http_client=client,
    ):
        docs.append(doc)
    await client.aclose()
    assert len(docs) == 1
