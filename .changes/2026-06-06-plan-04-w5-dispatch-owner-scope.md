Scope REST subscription dispatch to the authenticated API key so a `manage:subscriptions` caller can
only enqueue notifications for subscriptions it owns. The core dispatch service now requires an
explicit dispatch scope; trusted internal fan-out must request `internal_all_active` with a reason.
