# Worker entrypoints

The Python pipeline runs as **portable CLI entrypoints**, not host-specific functions. The
same command runs locally, in a GitHub Actions scheduled workflow (zero-cost on the public
OSS repo), in Modal, or under a VPS cron — this is what keeps the **scheduler choice
non-locking** (decision D11).

```bash
# Each service exposes jobs via `python -m <package> <job> [args]`:
uv run python -m intercal_ingest      ingest_source --source <id>
uv run python -m intercal_extract     extract_claims --document <id>
uv run python -m intercal_resolve     resolve_entities
uv run python -m intercal_synthesize  build_digest --topic <id>
```

The job set follows the foundation report's "Scheduling and Jobs". Every job is idempotent:
re-running must not duplicate documents, claims, relationships, or fact versions.

Scheduling is just *which* runner invokes these:

- **Local / dev** — run the command directly, or via the `SchedulerPort` local adapter.
- **Pilot (zero-cost)** — a scheduled GitHub Actions workflow (cron) on the public repo.
- **Spillover / GPU** — Modal invokes the same entrypoints.
- **VPS** — systemd timers / cron.

No worker contains deploy-target-specific logic; provider access is via the adapter ports in
`services/shared`.
