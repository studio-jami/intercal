Fix Plan 04 W5 subscription dispatch so claim-pattern notifications only enqueue for matching
patterns, dispatch targets are validated against their declared kind, and inactive subscriptions
cannot be polled or receive webhook deliveries.
