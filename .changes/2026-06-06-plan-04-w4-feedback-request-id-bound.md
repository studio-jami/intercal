Bound feedback request correlation metadata: `x-request-id` is now trimmed, capped at 128
characters, and rejected if it contains control characters before feedback review/audit rows are
stored.
