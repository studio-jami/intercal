# Provenance

Every publicly served fact must trace to evidence. The evidence chain is:

```text
source row -> source document -> claim evidence -> claim -> entity / relationship / fact version -> public response
```

## What public routes can show

Public pages and APIs may show:

- structured claims returned by the query layer;
- citations with `sourceDocumentId`, URL, and published date;
- source-document metadata returned by `get_sources`;
- derived snippets only when source policy permits;
- explicit unknown, stale, thin, unavailable, or coverage-gap states.

They must not show raw source bodies.

## Bitemporal behavior

Point-in-time reads use both valid-world time and transaction time. For example, `verify_claim` with `as_of_date` evaluates the claim against evidence available for that date and returns `unverified` rather than inventing support when the substrate has no matching cited evidence.

## Feedback

Feedback creates review records for operators. It does not mutate canonical claims, entities, relationships, or fact versions.

## Contradictions

Contradictions are explicit graph state. `verify_claim` uses recorded contradiction state and deterministic matching over cited evidence; it does not ask an LLM to decide unsupported facts from scratch.
