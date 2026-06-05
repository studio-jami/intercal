# Cloud Run image for the Intercal Python pipeline workers. Cloud-built — not for local use.
# Build context = repo root:  docker build -f docker/workers.Dockerfile -t intercal-workers .
# Run a job:  (Cloud Run Job / GitHub Actions)  uv run python -m intercal_ingest ingest_source ...
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY . .
RUN uv sync --all-packages --frozen
ENTRYPOINT ["uv", "run"]
CMD ["python", "-c", "print('intercal workers image — pass a job, e.g. python -m intercal_ingest <job>')"]
