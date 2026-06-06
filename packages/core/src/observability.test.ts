import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { OBSERVABILITY_VIEW_NAMES } from './observability.js';

describe('observability views', () => {
  it('keeps the core read helper aligned to the SQL-owned views', () => {
    const migration = readFileSync(
      resolve(process.cwd(), '..', '..', 'db', 'migrations', '0030_observability.sql'),
      'utf8',
    );
    const helper = readFileSync(resolve(process.cwd(), 'src', 'observability.ts'), 'utf8');

    for (const viewName of OBSERVABILITY_VIEW_NAMES) {
      expect(migration).toContain(`VIEW ${viewName}`);
      expect(helper).toContain(`selectView(db, '${viewName}'`);
    }
  });

  it('does not zero-fill missing provider telemetry', () => {
    const migration = readFileSync(
      resolve(process.cwd(), '..', '..', 'db', 'migrations', '0030_observability.sql'),
      'utf8',
    );

    expect(migration).toContain(
      'CASE WHEN u.last_observed_at IS NULL THEN NULL ELSE u.quantity_used END AS quantity_used',
    );
    expect(migration).toContain("WHEN u.last_observed_at IS NULL THEN 'unavailable'");
    expect(migration).toContain(
      "WHEN u.last_observed_at IS NULL THEN 'no provider usage event has been recorded'",
    );
  });
});
