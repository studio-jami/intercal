# Cloud Run image for the Intercal MCP server (Streamable HTTP). Cloud-built — not for local use.
# Build context = repo root:  docker build -f docker/mcp.Dockerfile -t intercal-mcp .
FROM node:24-slim AS build
RUN corepack enable
WORKDIR /app
COPY . .
RUN pnpm install --frozen-lockfile \
  && pnpm --filter @intercal/shared --filter @intercal/core --filter @intercal/mcp-server build \
  && pnpm deploy --filter @intercal/mcp-server --prod /app/out

FROM node:24-slim AS run
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/out /app
COPY --from=build /app/packages/shared/generated /app/node_modules/@intercal/shared/generated
EXPOSE 8788
ENV MCP_PORT=8788
CMD ["node", "dist/http.js"]
