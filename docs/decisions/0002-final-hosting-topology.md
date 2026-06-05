# 0002 — Final Hosting Topology

Status: **Accepted** — 2026-06-04
Refines: 0001 (D5/D6/D11/D15) with the concrete, decided go-live shape.

The full intended deployment shape, aimed at from the start. Free now; each layer scales (or
swaps) without re-architecture because everything sits behind a port or a standard contract.

| Concern | Decision | Rationale |
| --- | --- | --- |
| Database | **Neon** (Postgres + pgvector). Dev = a Neon **branch**; prod = main. | Direct-to-cloud development — **no Docker in the maintainers' flow**. Branch-per-env is free and instant. `pg` driver works from Vercel Node functions, Cloud Run, Actions, and local node alike. |
| App host (dashboard + REST API + MCP) | **Vercel**, one project / one domain. Hono mounts into Next.js (`/api/v1/*`); MCP at `/api/mcp` or the Cloud Run service. | Easiest GitHub-wired live loop with preview deploys + custom domain. Hono keeps it portable to Cloudflare later (contained swap). |
| Object storage | **Cloudflare R2** (S3 API). | Zero egress; preferred. Adapter targets the S3 API so AWS/MinIO/GCS swap freely. |
| Queue / cache | **Upstash** Redis. | Serverless, free tier; behind the queue port (pgmq fallback). |
| Heavy Python pipeline | **GitHub Actions** scheduled workflows (free, public repo) for batch; **GCloud Cloud Run** for on-demand/scale. | The pipeline (ML embeddings, LLM calls, long jobs) does not fit edge/serverless-light. Portable worker CLIs run unchanged on both. Cloud-built Docker (`docker/workers.Dockerfile`) — never run locally by maintainers. |
| CI/CD | GitHub → Vercel auto-deploy (preview per PR, prod on `main`) + Actions verify gate. | Fully wired; the repo is the control plane. |

## Notes

- **No local Docker for maintainers.** `docker/compose.yaml` and the Dockerfiles remain in the
  repo as a self-host path for *other people* and as Cloud Run build artifacts (built in the
  cloud). The maintainers develop directly against Neon.
- **Going live** needs only: connect repo → Vercel, set env (Neon/R2/Upstash/LLM), attach a
  domain. Until then we run on `*.vercel.app`.
- **Monetization/donations = a feature flag.** No donation copy or link is surfaced until the
  domain and posture are settled. This is a toggle, never an architectural constraint, and
  never blocks building or testing live.
- **Scale path:** Neon paid tier / Cloud Run autoscaling / managed Redis when usage demands —
  all config changes behind existing ports, no migration.
