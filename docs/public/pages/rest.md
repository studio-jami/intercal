# REST

REST is mounted under:

```text
https://intercal.jami.studio/api/v1
```

The generated OpenAPI document is served from:

```text
https://intercal.jami.studio/api/openapi.json
```

## Contract source

TypeSpec in `packages/shared/typespec/main.tsp` is the contract source. It generates OpenAPI 3.1, JSON Schema, TypeScript types, and the SDK type aliases. Docs link to the generated contract instead of duplicating schemas.

## Read endpoints

- `GET /v1/entity`
- `GET /v1/sources`
- `GET /v1/freshness`
- `GET /v1/evidence`
- `GET /v1/delta`
- `GET /v1/claims/verify`

## Feedback and subscriptions

Feedback creates audited review records and does not mutate canonical graph state:

- `POST /v1/feedback`

Subscription management requires an API key:

- `GET /v1/subscriptions`
- `POST /v1/subscriptions`
- `POST /v1/subscriptions/poll`
- `POST /v1/subscriptions/dispatch`
- `POST /v1/subscriptions/delete`

## Errors

Errors use the generated `ApiError` shape with `code`, `message`, and optional `details`. Known codes include `invalid_request`, `unauthorized`, `forbidden`, `not_found`, `rate_limited`, `not_implemented`, and `internal_error`.
