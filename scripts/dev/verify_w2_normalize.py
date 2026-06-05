"""W2 integration verification script — run normalize_document on all W1 docs.

Usage:
    DATABASE_URL=<neon_branch_url> uv run python scripts/dev/verify_w2_normalize.py

Do not commit DATABASE_URL as a secret. Use .env or pass via environment.
"""

from __future__ import annotations

import asyncio
import os
import sys


async def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL env var is required", file=sys.stderr)
        sys.exit(1)

    from intercal_ingest.jobs import normalize_document
    from intercal_shared.db import get_pool

    pool = await get_pool(database_url)

    # Fetch all document IDs
    rows = await pool.fetch("SELECT id FROM source_documents ORDER BY created_at")
    print(f"Found {len(rows)} documents to normalize")

    total_chunks = 0
    for row in rows:
        doc_id = str(row["id"])
        result = await normalize_document(
            document_id=doc_id,
            pool=pool,
            storage=None,
        )
        print(
            f"  doc={doc_id[:8]}... skipped={result['skipped']} "
            f"chunks={result['chunk_count']} lang={result['language']} "
            f"chars={result['clean_chars']}"
        )
        if not result["skipped"]:
            total_chunks += int(result["chunk_count"])  # type: ignore[arg-type]

    print(f"Total chunks produced: {total_chunks}")

    # Verify DB state
    docs = await pool.fetch("SELECT normalized_at, chunk_count FROM source_documents")
    all_normalised = all(r["normalized_at"] is not None for r in docs)
    print(f"All normalized_at set: {all_normalised}")
    chunks_in_db = await pool.fetchval("SELECT COUNT(*) FROM document_chunks")
    print(f"document_chunks rows in DB: {chunks_in_db}")

    if not all_normalised:
        print("FAIL: some documents were not normalised", file=sys.stderr)
        sys.exit(1)
    # chunk_count in source_documents must match actual chunk rows.
    expected_chunks = sum(r["chunk_count"] or 0 for r in docs)
    if chunks_in_db != expected_chunks:
        print(
            f"FAIL: DB chunk count {chunks_in_db} != "
            f"sum(source_documents.chunk_count)={expected_chunks}",
            file=sys.stderr,
        )
        sys.exit(1)

    print("PASS: W2 normalize path verified against Neon branch")


if __name__ == "__main__":
    asyncio.run(main())
