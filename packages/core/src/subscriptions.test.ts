import { describe, expect, it } from 'vitest';
import type { Db } from './db/client.js';
import { InvalidRequestError, NotFoundError } from './errors.js';
import {
  createSubscription,
  enqueueSubscriptionNotifications,
  pollSubscriptionNotifications,
} from './subscriptions.js';

function dbStub(overrides: Partial<Db> = {}): Db {
  return overrides as Db;
}

describe('subscription target validation', () => {
  it('rejects empty claim-pattern subscriptions before writing', async () => {
    await expect(
      createSubscription(dbStub(), {
        apiKeyId: 'key-1',
        actor: { type: 'api_key', id: 'key-1' },
        target: { kind: 'claim_pattern', claimPattern: {} },
        deliveryMethod: 'polling',
      }),
    ).rejects.toBeInstanceOf(InvalidRequestError);
  });

  it('rejects dispatch targets that do not match changeKind', async () => {
    await expect(
      enqueueSubscriptionNotifications(dbStub(), {
        actor: { type: 'api_key', id: 'key-1' },
        changeKind: 'topic',
        entityId: '22222222-2222-4222-8222-222222222222',
        sinceDate: '2026-06-01T00:00:00.000Z',
      }),
    ).rejects.toBeInstanceOf(InvalidRequestError);
  });

  it('does not broadcast a claim-pattern dispatch to non-matching claim-pattern subscribers', async () => {
    const rows = [
      {
        id: 'sub-1',
        api_key_id: 'key-1',
        topic_id: null,
        entity_id: null,
        relationship_type_id: null,
        source_id: null,
        claim_pattern: JSON.stringify({ predicate: 'founded', object: 'Intercal' }),
        min_importance: '0.00',
        token_budget: 1500,
        delivery_method: 'polling',
        webhook_url: null,
        webhook_secret_hash: null,
        is_active: true,
        last_delivered_at: null,
        last_checked_at: null,
        metadata: {},
        created_at: new Date('2026-06-01T00:00:00.000Z'),
        updated_at: new Date('2026-06-01T00:00:00.000Z'),
      },
    ];
    const db = dbStub({
      selectFrom() {
        const builder = {
          selectAll() {
            return builder;
          },
          where() {
            return builder;
          },
          limit() {
            return builder;
          },
          async execute() {
            return rows;
          },
        };
        return builder;
      },
    } as unknown as Db);

    await expect(
      enqueueSubscriptionNotifications(db, {
        actor: { type: 'api_key', id: 'key-1' },
        changeKind: 'claim_pattern',
        claimPattern: { predicate: 'holds_role', object: 'CEO' },
        sinceDate: '2026-06-01T00:00:00.000Z',
      }),
    ).resolves.toEqual({ enqueued: 0, skipped: 1 });
  });
});

describe('subscription active-state guards', () => {
  it('does not allow polling an inactive subscription', async () => {
    const inactive = {
      id: 'sub-1',
      api_key_id: 'key-1',
      is_active: false,
    };
    const db = dbStub({
      selectFrom() {
        const builder = {
          selectAll() {
            return builder;
          },
          where() {
            return builder;
          },
          async executeTakeFirst() {
            return inactive;
          },
        };
        return builder;
      },
    } as unknown as Db);

    await expect(
      pollSubscriptionNotifications(db, {
        apiKeyId: 'key-1',
        subscriptionId: 'sub-1',
      }),
    ).rejects.toBeInstanceOf(NotFoundError);
  });
});
