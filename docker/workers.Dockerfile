# Cloud Run image for the Intercal Python pipeline workers. Cloud-built — not for local use.
# Build context = repo root:  docker build -f docker/workers.Dockerfile -t intercal-workers .
# Default entrypoint runs the portable orchestrator CLI; a Cloud Run Job / GitHub Actions
# job overrides args, e.g.  intercal-pipeline run-all --max-documents 10
#
# Pinned base + uv for reproducible, small, cloud-built images (Plan 07 W4).
FROM python:3.12-slim
# Pin uv to an exact release (no moving `latest`) for reproducible cloud builds. `--frozen`
# resolves against uv.lock identically regardless of uv version, but pinning the binary keeps
# the image byte-stable. Bump in lockstep with the dev/CI toolchain.
COPY --from=ghcr.io/astral-sh/uv:0.10.9 /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY . .
# --all-extras pulls intercal-shared's runtime adapter extras (storage-s3/aioboto3,
# source-http, embeddings-local/fastembed, llm-gemini, queue-redis). Without them the
# real pipeline run fails at adapter construction (ImportError: aioboto3) — the same gap
# the GitHub Actions path (W3) hit. Mirror its `uv sync --all-packages --all-extras --frozen`.
RUN uv sync --all-packages --all-extras --frozen
# `intercal-pipeline` is the console script exposed by services/pipeline (cli:main).
# Cloud Run Jobs override the args (`--args`) to pass run-all|run + budget caps.
ENTRYPOINT ["uv", "run", "intercal-pipeline"]
CMD ["run-all"]
