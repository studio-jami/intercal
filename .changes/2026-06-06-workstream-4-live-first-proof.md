## Changed

- Added reviewed first-proof source catalog rows and an idempotent operator script that applies
  bounded GPT/Claude/Gemini/Llama/MCP proof corpus rows with source documents, claims, evidence,
  contradictions, and fact versions.
- Updated `verify_claim` `as_of_date` filtering to use historical valid-world time instead of claim
  row insertion time, allowing fresh historical backfills to answer point-in-time truth checks.
- Allowed the corpus quality verifier to load `DATABASE_URL` from local `.env` without printing it.
