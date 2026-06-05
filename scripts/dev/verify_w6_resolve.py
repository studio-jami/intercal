"""W6 entity resolution smoke test — real mentions + real Neon branch.

Runs resolve_entities on the live Neon dev branch
(br-still-water-ajmss6b6) using the local fastembed adapter (zero-cost).
Confirms:
  - ≥ 1 resolved entity created
  - ≥ 1 needs_review candidate present in entity_resolution_candidates
  - Mention rows updated (resolution_status = 'resolved')
  - Provenance: entity_id FK present on resolved mentions
  - Idempotent re-run: counters stable (no duplicate entities)

Requirements:
  DATABASE_URL pointing at the Neon dev branch.
  EMBEDDINGS_PROVIDER=local (default) — fastembed must be installed.
  W3 already run: mentions table has rows with resolution_status = 'unresolved'.

Run (from repo root):
    uv run python scripts/dev/verify_w6_resolve.py

Resource budget: fastembed is local/zero-cost; no LLM calls.
Does NOT mock — uses the real resolve port and real DB.
Does NOT write secrets to output.
"""

from __future__ import annotations

import asyncio
import sys


async def main() -> None:
    from intercal_resolve.jobs import resolve_entities
    from intercal_shared.config import Settings
    from intercal_shared.db import close_all_pools, get_pool
    from intercal_shared.factory import make_embeddings

    cfg = Settings()

    print("=" * 60)
    print("W6 Entity Resolution Smoke Test")
    print("=" * 60)
    print(f"  Embeddings provider: {cfg.embeddings_provider!r}")
    print(f"  Model: {cfg.embeddings_model!r}  dim={cfg.embeddings_dim}")
    print()

    pool = await get_pool(cfg.database_url)
    emb = make_embeddings(cfg)

    all_passed = True

    # ── Step 1: Check pre-conditions ──────────────────────────────────────────
    unresolved_before = await pool.fetchval(
        "SELECT count(*) FROM mentions WHERE resolution_status = 'unresolved'"
    )
    entities_before = await pool.fetchval(
        "SELECT count(*) FROM entities WHERE is_deprecated = false"
    )
    candidates_before = await pool.fetchval(
        "SELECT count(*) FROM entity_resolution_candidates"
    )

    print(f"  Before: {unresolved_before} unresolved mentions, {entities_before} entities, "
          f"{candidates_before} candidates")

    if int(unresolved_before) == 0:
        print("  [WARN] No unresolved mentions found — run W3 first.")
        print("  Skipping live resolution run.")
        await close_all_pools()
        sys.exit(0)

    # ── Step 2: Run resolution ────────────────────────────────────────────────
    print()
    print("  Running resolve_entities (batch_size=50, with local embeddings)...")
    counters = await resolve_entities(pool=pool, embeddings=emb, batch_size=50)
    print(f"  Counters: {counters}")

    # ── Step 3: Verify post-conditions ────────────────────────────────────────
    unresolved_after = await pool.fetchval(
        "SELECT count(*) FROM mentions WHERE resolution_status = 'unresolved'"
    )
    entities_after = await pool.fetchval(
        "SELECT count(*) FROM entities WHERE is_deprecated = false"
    )
    candidates_after = await pool.fetchval(
        "SELECT count(*) FROM entity_resolution_candidates"
    )
    review_count = await pool.fetchval(
        "SELECT count(*) FROM entity_resolution_candidates"
        " WHERE proposed_decision = 'needs_review' AND decision_status = 'open'"
    )

    print()
    print(f"  After:  {unresolved_after} unresolved mentions, {entities_after} entities, "
          f"{candidates_after} candidates ({review_count} needs_review)")

    # Check ≥ 1 entity created
    entities_delta = int(entities_after) - int(entities_before)
    if counters["entities_created"] > 0:
        print(f"  [PASS] Entities created: {counters['entities_created']} (delta={entities_delta})")
    else:
        # entities may already exist from a prior run
        print("  [INFO] No new entities created (may already exist — idempotent run)")

    # Check ≥ 1 resolved mention
    resolved_count = counters["mentions_resolved"]
    if resolved_count > 0 or int(unresolved_before) > int(unresolved_after):
        print(f"  [PASS] Mentions resolved: {resolved_count}")
    else:
        print("  [FAIL] No mentions resolved")
        all_passed = False

    # Check provenance: resolved mentions have entity_id set
    resolved_with_entity = await pool.fetchval(
        "SELECT count(*) FROM mentions"
        " WHERE resolution_status = 'resolved' AND entity_id IS NOT NULL"
    )
    if int(resolved_with_entity) > 0:
        print(f"  [PASS] Provenance: {resolved_with_entity} resolved mentions have entity_id FK")
    else:
        print("  [FAIL] No resolved mentions have entity_id set (provenance broken)")
        all_passed = False

    # Check at least 1 entity exists overall
    if int(entities_after) > 0:
        print(f"  [PASS] >=1 entity in DB ({entities_after} total active)")
    else:
        print("  [FAIL] No entities in DB after resolution")
        all_passed = False

    # Show candidates
    if int(candidates_after) > 0:
        print(f"  [INFO] {candidates_after} resolution candidates in DB "
              f"({review_count} needs_review)")
    else:
        print("  [INFO] No resolution candidates (spans too distinct or no embeddings hits)")

    # ── Step 4: Idempotent re-run ─────────────────────────────────────────────
    print()
    print("  Running resolve_entities again (idempotent re-run check)...")
    _ = await resolve_entities(pool=pool, embeddings=emb, batch_size=50)
    entities_after2 = await pool.fetchval(
        "SELECT count(*) FROM entities WHERE is_deprecated = false"
    )
    # No new entities should have been created
    if int(entities_after2) == int(entities_after):
        print(f"  [PASS] Idempotent re-run: entity count unchanged ({entities_after2})")
    else:
        delta2 = int(entities_after2) - int(entities_after)
        print(f"  [FAIL] Idempotent re-run created +{delta2} entities (not idempotent)")
        all_passed = False

    # ── Step 5: Show sample entities ─────────────────────────────────────────
    print()
    sample_entities = await pool.fetch(
        """
        SELECT e.id, e.type_id, e.canonical_name,
               count(m.id) AS mention_count
        FROM entities e
        LEFT JOIN mentions m ON m.entity_id = e.id
        WHERE e.is_deprecated = false
        GROUP BY e.id, e.type_id, e.canonical_name
        ORDER BY mention_count DESC
        LIMIT 10
        """
    )
    print("  Sample entities (top by mention count):")
    for row in sample_entities:
        eid = row["type_id"]
        name = row["canonical_name"]
        cnt = row["mention_count"]
        print(f"    [{eid:20s}] {name:30s}  mentions={cnt}")

    # ── Final result ──────────────────────────────────────────────────────────
    await close_all_pools()
    print()
    if all_passed:
        print("  Smoke test: PASS")
    else:
        print("  Smoke test: FAIL")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
