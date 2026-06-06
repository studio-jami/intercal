Backfill resume now reuses the newest recent ingestion cursor whose saved trigger and effective
adapter-config scope match the current run, so returning to an earlier historical date window resumes
that window instead of restarting after a different window ran later.
