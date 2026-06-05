"""Source registry — maps adapter_name strings to source adapter instances.

The registry is a lightweight in-process map.  Adapters self-register via
``register()`` or are loaded lazily by name via ``get()``.  No heavy imports
happen until the adapter is actually requested.

Usage
-----
    from intercal_shared.source_registry import registry
    adapter = registry.get("wikidata_changes_v1")

Adding a new adapter
--------------------
    # In the adapter module:
    from intercal_shared.source_registry import registry
    registry.register(MyAdapter())

Or call ``registry.register_all_defaults()`` at startup to load every
built-in adapter.

Adapter conformance contract
-----------------------------
Adapters must expose:
- ``adapter_name: str`` — unique registry key.
- ``async def fetch(*, adapter_config, cursor_state, max_documents, http_client)``
  — an async generator yielding ``RawDocument`` instances.

Conformance is verified by tests rather than enforced via strict typing,
because async generators cannot be cleanly typed as Protocol methods in
Python 3.12 without sacrificing readability.
"""

from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger(__name__)


class SourceRegistry:
    """In-process registry mapping adapter_name -> source adapter instance."""

    def __init__(self) -> None:
        self._adapters: dict[str, Any] = {}

    def register(self, adapter: Any) -> None:
        """Register *adapter* under its ``adapter_name``.

        The adapter must have an ``adapter_name: str`` attribute.
        """
        name: str = adapter.adapter_name
        if name in self._adapters:
            _log.warning("Overwriting existing source adapter %r", name)
        self._adapters[name] = adapter
        _log.debug("Registered source adapter %r", name)

    def get(self, adapter_name: str) -> Any:
        """Return the adapter registered for *adapter_name*.

        Raises
        ------
        KeyError
            If no adapter with that name has been registered.
        """
        try:
            return self._adapters[adapter_name]
        except KeyError:
            available = ", ".join(sorted(self._adapters)) or "(none)"
            raise KeyError(
                f"No source adapter registered for {adapter_name!r}. "
                f"Available adapters: {available}. "
                "Call registry.register_all_defaults() or register the adapter explicitly."
            ) from None

    def all_names(self) -> list[str]:
        """Return a sorted list of all registered adapter names."""
        return sorted(self._adapters)

    def register_all_defaults(self) -> None:
        """Instantiate and register all built-in adapters.

        Adapters are imported lazily here so optional dependencies are only
        loaded when the adapter is actually needed.
        """
        from intercal_shared.adapters.source_github import GitHubReleasesAdapter
        from intercal_shared.adapters.source_wikidata import WikidataChangesAdapter

        self.register(WikidataChangesAdapter())
        self.register(GitHubReleasesAdapter())
        _log.debug("Registered all default source adapters: %s", self.all_names())


# Module-level singleton shared across the process.
registry: SourceRegistry = SourceRegistry()
