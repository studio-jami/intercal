# Review Workflows

Intercal accepts bounded public feedback as review records. Feedback is an operations input only:
it never changes canonical entities, claims, sources, relationships, fact versions, digests, or
freshness/coverage calculations.

## Public Submission

Use `POST /v1/feedback` with a JSON body generated from the TypeSpec `FeedbackRequest` model:

- `targetType`: `entity`, `claim`, `source`, `digest`, `freshness`, or `coverage`
- `targetId`: canonical UUID for entity, claim, source, and digest targets; bounded target string
  for freshness and coverage targets
- `concernType`: `incorrect`, `outdated`, `missing_evidence`, `missing_coverage`,
  `source_quality`, `contradiction`, or `other`
- `summary`: required, 1-240 characters
- `details`: optional, up to 4000 characters

Anonymous callers may submit under the anonymous rate limit. If an API key is supplied, it must
include `submit:feedback`; `admin` also satisfies the scope rule. A key that has only `read` is
rejected for feedback submission.

The SDK sends feedback submissions once and does not apply automatic transient retries to this
POST. A retry after an ambiguous network failure is an explicit caller choice, because successful
submissions create review records.

## Stored Records

Submissions create one `review_records` row with status `received`. Entity, claim, source, and
digest targets must be UUIDs and are checked against their backing tables before a record is
accepted. Freshness and coverage targets are query concerns rather than canonical rows, so their
target is stored as a bounded string.

The creation event is written to `audit_events` as `feedback.submit` in the same transaction as the
review record. The audit row targets the review record, includes safe target metadata, and does not
store secrets or raw credentials.

## Status Workflow

Statuses are:

- `received`: accepted and awaiting operator review
- `reviewing`: an operator has started evaluation
- `resolved`: operator action or explanation completed
- `rejected`: not actionable, duplicate, abusive, or outside scope

The public API creates only `received` records. Operator status transitions belong to the later
review console and must also use `audit_events`; do not add direct graph mutation to feedback
submission.

## Canonical-State Boundary

Feedback may inform later operator-governed work, but it does not mutate:

- `entities`
- `claims`
- `sources`
- `relationships`
- `fact_versions`
- `digests`

Tests for the feedback route snapshot canonical tables before submission and assert they are
unchanged after the review and audit rows are created.
