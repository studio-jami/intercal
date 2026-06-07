# SDK

The TypeScript SDK is `@intercal/sdk`. It is a thin client over the generated REST contract and does not declare domain shapes of its own.

## Install from this workspace

Inside the monorepo, packages consume it through the pnpm workspace:

```json
{
  "dependencies": {
    "@intercal/sdk": "workspace:*"
  }
}
```

Published package installation is a release concern. Until a package is published, external consumers should use REST or vendor the workspace intentionally.

## Client

```ts
import { IntercalClient } from "@intercal/sdk";

const client = new IntercalClient({
  baseUrl: "https://intercal.jami.studio/api",
  maxRetries: 2,
  retryBackoffMs: 250,
});

const verification = await client.verifyClaim({
  claim_text: "GPT-4 Turbo supports a 128k context window",
  as_of_date: "2024-04-01T00:00:00Z",
});
```

## API keys

Pass a key only when you need raised limits or scoped surfaces:

```ts
const client = new IntercalClient({
  baseUrl: "https://intercal.jami.studio/api",
  apiKey: process.env.INTERCAL_API_KEY,
});
```

Do not commit raw keys. The server stores only key hashes and never returns a raw key after issuance.
