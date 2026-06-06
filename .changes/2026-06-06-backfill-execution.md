## Added

- Added `intercal-pipeline backfill` for bounded, date-windowed historical execution through the normal pipeline stages, with source ID/slug allowlists, source-class and adapter filters, per-source caps, source caps, and dry-run selection output.

## Changed

- Namespaced ingestion cursor state by trigger and effective adapter config so historical backfill cursors do not collide with scheduled ingestion or changed date windows.
- Exposed backfill controls in the scheduled pipeline GitHub Actions workflow and documented matching Cloud Run Job invocations.
