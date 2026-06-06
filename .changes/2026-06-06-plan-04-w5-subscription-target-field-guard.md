Reject off-contract nested subscription target and dispatch fields before they can be ignored by
the runtime, and reject webhook-only fields on polling subscriptions so unused webhook secrets are
not hashed or persisted.
