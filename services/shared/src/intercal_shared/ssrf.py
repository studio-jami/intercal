"""SSRF-safe outbound HTTP fetch guard.

Any time the substrate fetches an **externally-influenced URL** — an operator-
configured source endpoint today, a user-submitted source URL once that surface
exists (Plan 04 W4 feedback / Plan 06) — the fetch must be guarded against
Server-Side Request Forgery (SSRF): an attacker-controlled URL that points the
fetcher at internal services, the cloud metadata endpoint, or other private
infrastructure.

This module is a **port/util** behind which all such fetches funnel. It does
not own provider logic; it owns one cross-cutting safety concern (validating a
URL + the IP it resolves to, and pinning the connection so a later DNS answer
cannot redirect it).

What it enforces (aligned with the OWASP *SSRF Prevention Cheat Sheet*):

- **Scheme allowlist** — only ``http`` / ``https`` (configurable). No ``file:``,
  ``gopher:``, ``ftp:``, ``data:``, etc.
- **Host → IP resolution then IP validation** — the hostname is resolved (all
  A / AAAA records) and *every* resolved address is checked against the blocked
  ranges. A public hostname whose DNS answer is a private IP is rejected. Bare
  IP literals (incl. decimal / octal / hex / IPv4-mapped-IPv6 encodings) are
  parsed by :mod:`ipaddress`, which canonicalises those encodings, so
  ``0x7f.1`` / ``2130706433`` / ``0177.0.0.1`` all resolve to ``127.0.0.1`` and
  are blocked.
- **Blocked ranges** — loopback, private (RFC1918), link-local (incl. the
  ``169.254.169.254`` cloud metadata address used by AWS/GCP/Azure), unique-
  local IPv6 (``fc00::/7``), IPv6 link-local (``fe80::/10``), multicast,
  unspecified (``0.0.0.0`` / ``::``), reserved, and the IPv4-mapped /
  6to4 / Teredo embedding ranges that can smuggle a private IPv4 inside IPv6.
- **DNS-rebinding defence** — the validated IP is **pinned**: the actual socket
  connects to the exact address that passed validation, not whatever a second
  DNS lookup would return (closing the resolve-then-connect TOCTOU window).
- **Redirect re-validation** — redirects are **not** auto-followed by the
  transport; each hop's ``Location`` is re-validated through the same guard and
  followed manually up to a bounded hop count, so a public URL cannot 302 to
  ``http://169.254.169.254/``.
- **Timeouts & size caps** — every request carries a connect/read timeout and a
  maximum response-body size, so a hostile or pathological endpoint cannot hang
  the worker or exhaust memory.

The public entrypoints are :class:`SsrfPolicy` (the rules),
:func:`assert_url_allowed` (validate a URL string, returning the pinned IPs),
and :func:`create_guarded_client` (an ``httpx.AsyncClient`` whose transport
pins every connection to a validated IP and re-validates redirects).

``httpx`` is an optional dependency (``intercal-shared[source-http]``); it is
imported lazily so importing this module never forces the dependency.
"""

from __future__ import annotations

import dataclasses
import ipaddress
import socket
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:  # pragma: no cover - typing only
    import httpx

__all__ = [
    "DEFAULT_POLICY",
    "ResolvedTarget",
    "SsrfError",
    "SsrfPolicy",
    "assert_url_allowed",
    "create_guarded_client",
    "resolve_and_validate",
]

_DEFAULT_ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})

# Cloud instance-metadata service address shared by AWS, GCP and Azure IMDS.
# It is inside 169.254.0.0/16 (link-local) which we block wholesale, but we name
# it explicitly so the rejection reason is unambiguous in logs/tests.
_METADATA_IPV4 = ipaddress.ip_address("169.254.169.254")


class SsrfError(Exception):
    """Raised when a URL or its resolved address violates the SSRF policy.

    Carries a machine-stable :attr:`reason` so callers/tests can assert on the
    category without string-matching the human message.
    """

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclasses.dataclass(frozen=True)
class SsrfPolicy:
    """Rules governing which outbound URLs an externally-influenced fetch may reach.

    Attributes
    ----------
    allowed_schemes:
        URL schemes permitted. Default: ``{"http", "https"}``.
    allow_private:
        If ``True``, private / loopback / link-local addresses are permitted.
        **Only** for trusted self-host fetches against a private network; never
        enable for user-submitted URLs. Default ``False``.
    max_redirects:
        Maximum number of redirect hops to follow, each re-validated. Default 5.
    connect_timeout / read_timeout:
        Per-request socket timeouts in seconds.
    max_bytes:
        Maximum response body size accepted, in bytes. Default 16 MiB.
    """

    allowed_schemes: frozenset[str] = _DEFAULT_ALLOWED_SCHEMES
    allow_private: bool = False
    max_redirects: int = 5
    connect_timeout: float = 10.0
    read_timeout: float = 30.0
    max_bytes: int = 16 * 1024 * 1024

    def is_ip_blocked(self, ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
        """Return a blocking reason for *ip*, or ``None`` if it is allowed.

        Validates against the full hostile matrix. IPv4-mapped and 6to4 / Teredo
        IPv6 addresses are unwrapped to their embedded IPv4 and re-checked, so a
        private IPv4 smuggled inside an IPv6 literal is still blocked.
        """
        if self.allow_private:
            return None

        # Unwrap IPv6 that embeds an IPv4 (``::ffff:10.0.0.1``, 6to4 ``2002::``,
        # Teredo ``2001:0::``) and re-validate the embedded address.
        if isinstance(ip, ipaddress.IPv6Address):
            mapped = ip.ipv4_mapped or ip.sixtofour or (ip.teredo[1] if ip.teredo else None)
            if mapped is not None:
                inner = self.is_ip_blocked(mapped)
                if inner is not None:
                    return inner

        if ip == _METADATA_IPV4:
            return "cloud_metadata"
        # Order matters: ``is_private`` is a superset that also covers the
        # unspecified (``0.0.0.0`` / ``::``), loopback and link-local blocks, so
        # the more-specific checks must come first to return a precise reason.
        if ip.is_unspecified:  # 0.0.0.0 / ::
            return "unspecified"
        if ip.is_loopback:
            return "loopback"
        if ip.is_link_local:  # 169.254.0.0/16 and fe80::/10
            return "link_local"
        if ip.is_multicast:
            return "multicast"
        if ip.is_private:  # RFC1918, fc00::/7 ULA, and other private blocks
            return "private"
        if ip.is_reserved:
            return "reserved"
        if not ip.is_global:
            # Catch-all for anything not globally routable (e.g. 0.0.0.0/8,
            # 192.0.0.0/24, benchmarking ranges) that the specific checks missed.
            return "non_global"
        return None


DEFAULT_POLICY = SsrfPolicy()


@dataclasses.dataclass(frozen=True)
class ResolvedTarget:
    """A URL that passed validation, with the concrete IPs it resolved to."""

    scheme: str
    host: str
    port: int
    #: Validated IP literals (as strings) the host resolved to. The connection
    #: must be pinned to one of these to defeat DNS rebinding.
    ip_addresses: tuple[str, ...]


def _normalise_host(host: str) -> str:
    """Strip IPv6 brackets and a trailing dot from a URL hostname."""
    h = host.strip()
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    return h.rstrip(".")


def _try_parse_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Parse *host* as an IP literal, canonicalising alternate encodings.

    ``ipaddress.ip_address`` only accepts the canonical dotted-quad / colon
    forms, so an attacker can dodge a naive textual blocklist with a decimal
    (``2130706433``), hex (``0x7f000001``), octal (``0177.0.0.1``) or short
    (``127.1``) encoding of a private address. We canonicalise those here so
    the IP-range check below sees the real address — defence-in-depth on top of
    the OS resolver (which also canonicalises them via ``getaddrinfo``).

    Returns ``None`` when *host* is not an IP literal in any recognised form, so
    the caller falls through to DNS resolution for genuine hostnames.
    """
    # Canonical form first (covers all IPv6 and dotted-quad IPv4).
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass

    # Alternate IPv4 encodings. ``inet_aton`` accepts decimal/octal/hex and the
    # short ``a.b``/``a.b.c``/``a`` forms exactly as libc (and thus a browser /
    # the OS resolver) would interpret them. We only treat it as an IP literal
    # when the whole host is made of IPv4-ish characters, so a real hostname
    # like ``0x.example.com`` is not mis-parsed.
    if host and all(c in "0123456789abcdefABCDEFxX." for c in host):
        try:
            packed = socket.inet_aton(host)
        except OSError:
            return None
        return ipaddress.IPv4Address(packed)
    return None


def _resolve_host(host: str, port: int) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Resolve *host* to all A/AAAA addresses via the OS resolver.

    A literal IP (in any encoding) short-circuits resolution. Returns at least
    one address or raises :class:`SsrfError` with reason ``dns``.
    """
    literal = _try_parse_ip(host)
    if literal is not None:
        return [literal]

    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise SsrfError(f"could not resolve host {host!r}: {exc}", reason="dns") from exc

    addrs: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    seen: set[str] = set()
    for info in infos:
        sockaddr = info[4]
        # sockaddr[0] is the address; getaddrinfo types it str|int, but for the
        # IP families it is always the canonical IP string.
        ip_str = str(sockaddr[0])
        if ip_str in seen:
            continue
        seen.add(ip_str)
        # getaddrinfo returns canonical IP strings; scoped IPv6 (fe80::%eth0)
        # carries a zone we strip before parsing.
        try:
            addrs.append(ipaddress.ip_address(ip_str.split("%", 1)[0]))
        except ValueError:  # pragma: no cover - getaddrinfo should not emit garbage
            continue
    if not addrs:
        raise SsrfError(f"host {host!r} resolved to no usable addresses", reason="dns")
    return addrs


def resolve_and_validate(url: str, policy: SsrfPolicy = DEFAULT_POLICY) -> ResolvedTarget:
    """Validate *url* against *policy*, resolving and checking every IP.

    Returns a :class:`ResolvedTarget` carrying the validated IPs to pin the
    connection to. Raises :class:`SsrfError` on any violation.
    """
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in policy.allowed_schemes:
        raise SsrfError(
            f"scheme {scheme!r} not allowed (allowed: {sorted(policy.allowed_schemes)})",
            reason="scheme",
        )

    raw_host = parts.hostname
    if not raw_host:
        raise SsrfError(f"URL {url!r} has no host", reason="no_host")
    host = _normalise_host(raw_host)
    if not host:
        raise SsrfError(f"URL {url!r} has an empty host", reason="no_host")

    try:
        port = parts.port or (443 if scheme == "https" else 80)
    except ValueError as exc:
        # urlsplit raises on a non-integer port (``http://h:notaport/``).
        raise SsrfError(f"URL {url!r} has an invalid port", reason="port") from exc

    addresses = _resolve_host(host, port)
    for ip in addresses:
        reason = policy.is_ip_blocked(ip)
        if reason is not None:
            raise SsrfError(
                f"host {host!r} resolves to blocked address {ip} ({reason})",
                reason=reason,
            )

    return ResolvedTarget(
        scheme=scheme,
        host=host,
        port=port,
        ip_addresses=tuple(str(ip) for ip in addresses),
    )


def assert_url_allowed(url: str, policy: SsrfPolicy = DEFAULT_POLICY) -> ResolvedTarget:
    """Alias for :func:`resolve_and_validate` reading as a guard assertion.

    Use when you only need the side-effect (raise on violation) but the return
    value — the validated/pinned IPs — is still useful to the caller.
    """
    return resolve_and_validate(url, policy)


# ──────────────────────────────────────────────────────────────────────────────
# httpx integration: a transport that pins connections to validated IPs and
# re-validates redirects.
# ──────────────────────────────────────────────────────────────────────────────


def create_guarded_client(
    policy: SsrfPolicy = DEFAULT_POLICY,
    *,
    headers: dict[str, str] | None = None,
    **client_kwargs: object,
) -> httpx.AsyncClient:
    """Return an ``httpx.AsyncClient`` that enforces *policy* on every request.

    The returned client:

    - validates each request URL (scheme + resolved-IP blocklist) before the
      socket is opened, and **pins** the connection to the validated IP so a
      racing DNS answer cannot rebind it to a private address;
    - never auto-follows redirects (``follow_redirects=False`` is forced); use
      :func:`guarded_get` for redirect-following with per-hop re-validation, or
      handle 3xx explicitly;
    - applies the policy's connect/read timeouts.

    ``headers`` and other ``httpx.AsyncClient`` kwargs are forwarded. Callers
    must still bound response size via :func:`read_capped` / ``max_bytes``.

    Raising on a borrowed/shared client is avoided by giving each guarded client
    its own pinning transport.
    """
    import httpx

    timeout = httpx.Timeout(
        connect=policy.connect_timeout,
        read=policy.read_timeout,
        write=policy.read_timeout,
        pool=policy.connect_timeout,
    )
    transport = _make_pinning_transport(policy)
    # follow_redirects is forced off: redirects bypass per-request validation,
    # so they must be re-validated by the caller (guarded_get does this).
    client_kwargs.pop("follow_redirects", None)
    client_kwargs.pop("transport", None)
    client_kwargs.pop("timeout", None)
    return httpx.AsyncClient(
        transport=transport,
        timeout=timeout,
        follow_redirects=False,
        headers=headers,
        **client_kwargs,  # type: ignore[arg-type]
    )


def _make_pinning_transport(policy: SsrfPolicy) -> httpx.AsyncBaseTransport:
    """Build an httpx async transport that validates + pins each request to a safe IP.

    The transport subclasses ``httpx.AsyncBaseTransport`` and wraps an inner
    ``httpx.AsyncHTTPTransport``. Before delegating, it validates the request URL
    through *policy* and rewrites the connection target to the validated IP while
    preserving the ``Host`` header and TLS SNI to the original hostname — closing
    the resolve→connect DNS-rebinding window so the OS never gets a second chance
    to resolve the hostname to a different (private) address.

    The class is defined here (not at module scope) because ``httpx`` is an
    optional dependency imported lazily; defining the subclass at call time keeps
    the import lazy while still giving callers a proper ``AsyncBaseTransport``.
    """
    import httpx

    class _PinningAsyncTransport(httpx.AsyncBaseTransport):
        def __init__(self, policy: SsrfPolicy) -> None:
            self._policy = policy
            self._inner = httpx.AsyncHTTPTransport(retries=0)

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            target = resolve_and_validate(str(request.url), self._policy)

            original_host = request.url.host
            # Pin the URL host to the first validated address so the socket
            # connects to exactly the IP we validated. Preserve Host + SNI.
            pinned_ip = target.ip_addresses[0]
            host_for_url = f"[{pinned_ip}]" if ":" in pinned_ip else pinned_ip

            pinned_url = request.url.copy_with(host=host_for_url)
            headers = httpx.Headers(request.headers)
            if "host" not in {k.lower() for k in headers}:
                port = request.url.port
                headers["Host"] = original_host if port is None else f"{original_host}:{port}"

            pinned_request = httpx.Request(
                method=request.method,
                url=pinned_url,
                headers=headers,
                stream=request.stream,
                extensions={
                    **request.extensions,
                    # Force TLS SNI / cert verification against the real hostname,
                    # not the IP literal, so HTTPS to a pinned IP still validates.
                    "sni_hostname": original_host,
                },
            )
            return await self._inner.handle_async_request(pinned_request)

        async def aclose(self) -> None:
            await self._inner.aclose()

    return _PinningAsyncTransport(policy)


async def guarded_get(
    client: httpx.AsyncClient,
    url: str,
    policy: SsrfPolicy = DEFAULT_POLICY,
    *,
    headers: dict[str, str] | None = None,
    params: object | None = None,
) -> httpx.Response:
    """GET *url* on *client*, following redirects with per-hop SSRF re-validation.

    Each ``Location`` is re-validated through *policy* before being followed, up
    to ``policy.max_redirects`` hops, so a validated public URL cannot redirect
    the fetcher to a private/metadata address. The supplied *client* must be one
    returned by :func:`create_guarded_client` (it validates+pins every hop too;
    this function adds the bounded, re-validated redirect walk on top).
    """
    import httpx

    current = url
    for _hop in range(policy.max_redirects + 1):
        # The pinning transport validates `current` again before connecting.
        response = await client.get(current, headers=headers, params=params)  # type: ignore[arg-type]
        if response.status_code not in (301, 302, 303, 307, 308):
            return response
        location = response.headers.get("location")
        if not location:
            return response
        # Resolve relative redirects against the current URL, then re-validate.
        current = str(httpx.URL(current).join(location))
        resolve_and_validate(current, policy)
    raise SsrfError(
        f"exceeded {policy.max_redirects} redirects starting from {url!r}",
        reason="too_many_redirects",
    )


async def read_capped(response: httpx.Response, max_bytes: int) -> bytes:
    """Read *response* body, raising :class:`SsrfError` if it exceeds *max_bytes*.

    Streams so a hostile endpoint advertising a small ``Content-Length`` but
    sending more cannot exhaust memory before the cap trips.
    """
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > max_bytes:
            await response.aclose()
            raise SsrfError(
                f"response body exceeded {max_bytes} bytes",
                reason="too_large",
            )
        chunks.append(chunk)
    return b"".join(chunks)
