Reject malformed UUID-backed subscription targets and subscription IDs before they reach Postgres
UUID columns, keeping topic/entity create/dispatch and poll/delete failures on the bounded
`invalid_request` path.
