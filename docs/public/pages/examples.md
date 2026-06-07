# Examples

These examples use the generated contract and the live V1 operation names. They are checked by `pnpm docs:check` for route and operation drift.

## REST: delta

```http
GET /api/v1/delta?topic=frontier%20LLMs&since_date=2023-03-01T00:00:00Z&token_budget=300
Host: intercal.jami.studio
Accept: application/json
```

## REST: claim verification

```http
GET /api/v1/claims/verify?claim_text=GPT-4%20Turbo%20supports%20a%20128k%20context%20window&as_of_date=2024-04-01T00:00:00Z
Host: intercal.jami.studio
Accept: application/json
```

## SDK: same calls

```ts
import { IntercalClient } from "@intercal/sdk";

const client = new IntercalClient({ baseUrl: "https://intercal.jami.studio/api" });

const delta = await client.getDelta({
  topic: "frontier LLMs",
  since_date: "2023-03-01T00:00:00Z",
  token_budget: 300,
});

const verification = await client.verifyClaim({
  claim_text: "GPT-4 Turbo supports a 128k context window",
  as_of_date: "2024-04-01T00:00:00Z",
});
```

## MCP: tool call payloads

```json
{
  "name": "get_delta",
  "arguments": {
    "topic": "frontier LLMs",
    "since_date": "2023-03-01T00:00:00Z",
    "token_budget": 300
  }
}
```

```json
{
  "name": "verify_claim",
  "arguments": {
    "claim_text": "GPT-4 Turbo supports a 128k context window",
    "as_of_date": "2024-04-01T00:00:00Z"
  }
}
```

## OpenAPI

Fetch the generated contract instead of copying schemas from this page:

```powershell
Invoke-WebRequest "https://intercal.jami.studio/api/openapi.json" -UseBasicParsing
```
