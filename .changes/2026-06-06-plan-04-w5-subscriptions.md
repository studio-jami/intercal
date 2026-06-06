# Plan 04 W5 — subscriptions

Date: 2026-06-06
Type: feature
Packages: @intercal/core, @intercal/api, @intercal/shared

## Summary

Added scoped subscription management and bounded notification delivery support for topic, entity,
relationship, and claim-pattern changes.

## Changes

- Added `subscription_notifications` and `subscription_delivery_logs` as the notification outbox and
  delivery-attempt ledger.
- Added TypeSpec contract routes for create/list/poll/dispatch/delete subscription operations and
  regenerated OpenAPI, JSON Schema, TypeScript, and Pydantic artifacts.
- Added core subscription services for create/list/deactivate/enqueue/poll plus a
  `WebhookDeliveryPort` dispatcher with retry/backoff and delivery logs.
- Gated `/v1/subscriptions*` behind `manage:subscriptions` while preserving public read posture for
  the knowledge surface.
- Added durable operations/data-model docs and updated Plan 04 Workstream 5 status.

## Verification

- `pnpm contracts:build`
- `pnpm --filter @intercal/shared build`
- `pnpm --filter @intercal/core typecheck`
- `pnpm --filter @intercal/api typecheck`
- `pnpm --filter @intercal/core test`
- `pnpm --filter @intercal/api test`
