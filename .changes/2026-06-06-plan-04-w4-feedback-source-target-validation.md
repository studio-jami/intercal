Plan 04 W4 feedback now rejects non-UUID source targets before the database query path, so
malformed source feedback returns a bounded `invalid_request` response instead of risking a DB
syntax error. Review workflow docs now state that entity, claim, source, and digest feedback
targets use canonical UUIDs.
