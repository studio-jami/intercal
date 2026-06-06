# Subscriptions

Subscriptions let authenticated consumers register interest in knowledge changes without polling
the broad read surface. They are operational delivery records only; canonical graph state remains in
claims, relationships, entities, and fact versions.

## Access

REST subscription routes require an API key with `manage:subscriptions`. Public anonymous reads are
not enough.

- `GET /v1/subscriptions` lists the caller's active subscriptions.
- `POST /v1/subscriptions` creates a polling or webhook subscription.
- `POST /v1/subscriptions/poll` returns pending polling notifications and marks them delivered.
- `POST /v1/subscriptions/dispatch` enqueues bounded notifications after a known knowledge change.
- `POST /v1/subscriptions/delete` deactivates a subscription owned by the caller.

## Targets

A subscription has exactly one target:

- `topicId`
- `entityId`
- `relationshipTypeId`
- `claimPattern`

The API rejects registrations with no target or multiple targets. Topic/entity notifications reuse
the shared delta service; relationship and claim-pattern dispatch are matched through the same
notification outbox path and should stay grounded in public response shapes.

## Payload Bounds

Each notification stores a public-contract payload:

- token-budgeted delta summary
- changed claim IDs
- changed entity summaries
- confidence and freshness
- citations already allowed by the public contract

Notification payloads must not contain webhook secrets, raw API keys, source body text beyond the
source-policy gates, unrestricted internal rows, or provider-specific delivery metadata.

`minImportance` is copied to the outbox at enqueue time. Current importance is the maximum of
changed-entity signal, changed-claim confidence, and aggregate delta confidence. Changes below the
threshold are skipped.

## Webhooks

Webhook subscriptions accept `webhookUrl` only over HTTPS. `webhookSecret` is accepted only at
create time and stored as a SHA-256 hash; the plaintext is never persisted or returned.

Delivery is executed through `WebhookDeliveryPort` in `@intercal/core`, not by embedding provider
logic in the query layer. The port receives only the webhook URL, notification/subscription IDs, and
the bounded public payload. Delivery attempts update `subscription_notifications` and append
`subscription_delivery_logs` rows with status, HTTP status, error code, error message, and next
attempt time.

Retry backoff is exponential and capped: 1 minute, 2 minutes, 4 minutes, and so on up to 1 hour,
with a maximum of 5 attempts.

## Polling

Polling reads pending `polling` notifications for a subscription owned by the caller, marks returned
rows delivered, updates the subscription's checked/delivered timestamps, and writes one delivery log
row per returned notification.

## Audit

Subscription create/delete writes audit events in the same transaction as the subscription mutation:

- `subscription.create`
- `subscription.delete`

Audit metadata records target kind, delivery method, min importance, token budget, and whether a
webhook secret hash exists. It never records raw secrets.
