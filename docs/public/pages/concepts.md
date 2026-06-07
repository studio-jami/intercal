# Concepts

Intercal models knowledge as cited temporal state, not as free-form summaries.

## Source documents

A source document is an immutable evidence unit from an adapter-backed source. Source rows carry license and redistribution posture. Source documents snapshot that posture at ingest time so later policy edits do not silently rewrite what may be exposed.

## Claims

A claim is an atomic factual assertion extracted from source evidence. Claims carry confidence, status, contradiction state, valid-world time, and transaction time. Public claim output must include citation paths or an explicit unavailable state.

## Entities

Entities are conservative resolutions of mentions into canonical things: organizations, products, events, concepts, legislation, technical artifacts, datasets, jurisdictions, people, roles, and sources. False merges are corruption, so resolution is intentionally conservative.

## Relationships

Relationships are typed temporal edges between entities. They are derived from claims and evidence, not invented by the UI. Relationship status and valid-time windows make point-in-time reads possible.

## Fact versions

Fact versions are append-only bitemporal records. They let Intercal answer both "what was true in the world at this date?" and "what had Intercal recorded by this date?"

## Digests

Digests are delivery artifacts, not canonical facts. `get_delta` produces token-budgeted cited summaries over already-recorded evidence and graph state. The digest does not become the source of truth.
