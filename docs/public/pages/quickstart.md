# Quickstart

Use Intercal from the public UI first, then choose REST, SDK, or MCP for agent/application access.

## 1. Open the public surface

Go to `https://intercal.jami.studio`.

Useful starting routes:

- `/entity/ChatGPT`
- `/topic/frontier%20LLMs`
- `/delta?topic=frontier%20LLMs&since=2023-03-01T00:00:00Z`
- `/verify?claim=GPT-4%20Turbo%20supports%20a%20128k%20context%20window`
- `/coverage`

## 2. Fetch the generated contract

```powershell
Invoke-WebRequest "https://intercal.jami.studio/api/openapi.json" -UseBasicParsing
```

The OpenAPI document is generated from TypeSpec. Do not copy schemas out of docs prose; use the generated contract.

## 3. Call REST

```powershell
$base = "https://intercal.jami.studio/api"
Invoke-WebRequest "$base/v1/freshness?topic_or_entity=MCP%20protocol" -UseBasicParsing
```

Anonymous reads are allowed under a tight per-IP limit. A valid API key raises the rate limit and is required for subscription management.

## 4. Use the SDK

```ts
import { IntercalClient } from "@intercal/sdk";

const client = new IntercalClient({ baseUrl: "https://intercal.jami.studio/api" });
const delta = await client.getDelta({
  topic: "frontier LLMs",
  since_date: "2023-03-01T00:00:00Z",
  token_budget: 300,
});
```

## 5. Connect an MCP client

Point an MCP Streamable HTTP client at:

```text
https://intercal.jami.studio/api/mcp
```

The server exposes the same V1 query semantics as REST through generated JSON Schema tool inputs.
