"""
check_schema_drift.py
Fail loudly when the database and the embedding configuration disagree.

Why this exists
---------------
The embedding dimension is declared in three places that have no way of
checking each other: EMBEDDING_DIMS in embeddings.py, the `vector(N)` column on
document_chunks, and the `vector(N)` argument of the match_document_chunks RPC.
Switching provider — as this project did, from a 1536-dim model to a 512-dim one
— means changing all three, and nothing enforces that they moved together.

The failure is quiet in the worst way. A dimension mismatch does not corrupt
data; PostgREST rejects the write, ingest reports an error nobody reads, and the
table simply stays empty. Retrieval then returns nothing at all, which looks
like a bad model or an unlucky query rather than a schema problem. This project
has been in exactly that state: six documents ingested, zero chunks.

So this checks what is actually in the database against what the current
configuration produces, and exits non-zero on any disagreement. Cheap enough to
run in CI, before an ingest, or after a migration.

    python backend/check_schema_drift.py
"""

from __future__ import annotations

import sys

import config  # noqa: F401 - loads the repo-root .env
import embeddings
from db_client import get_supabase_client


def _fail(msg: str) -> None:
    print(f"  FAIL  {msg}")


def _ok(msg: str) -> None:
    print(f"  ok    {msg}")


def main() -> int:
    problems = 0
    client = get_supabase_client()

    expected = embeddings.expected_dimension()
    print(f"configuration: {embeddings.EMBEDDING_PROVIDER} / "
          f"{embeddings.EMBEDDING_MODEL} -> {expected}-dim")

    if expected is None:
        _fail(f"{embeddings.EMBEDDING_MODEL} is not in EMBEDDING_DIMS, so nothing "
              f"can be verified against it. Add it there first.")
        return 1

    # ── 1. Does the provider still return what EMBEDDING_DIMS claims? ────────
    # A provider can change a model's output width without renaming it, which
    # would leave every other check here agreeing with each other and with
    # nothing real.
    try:
        actual = len(embeddings.embed_texts(["dimension probe"])[0])
        if actual == expected:
            _ok(f"provider returns {actual}-dim vectors")
        else:
            _fail(f"provider returned {actual}-dim vectors but EMBEDDING_DIMS "
                  f"says {expected}")
            problems += 1
    except Exception as exc:  # noqa: BLE001 - any provider failure is a failure
        _fail(f"could not reach the embedding provider: {type(exc).__name__}: {exc}")
        problems += 1

    # ── 2. Does the stored data match? ──────────────────────────────────────
    # Read one row back rather than inspecting the column type: the length of a
    # vector that is actually in the table is the thing retrieval depends on,
    # and it catches rows written under an older configuration that a DDL check
    # would miss.
    res = client.table("document_chunks").select("id,embedding").limit(1).execute()
    rows = res.data or []
    if not rows:
        _fail("document_chunks is empty — retrieval will return nothing for "
              "every query. Run: python backend/ingest.py --dir ../sample_docs")
        problems += 1
    else:
        emb = rows[0]["embedding"]
        # PostgREST serialises pgvector as a string like "[0.1,0.2,...]".
        stored = len(emb) if isinstance(emb, list) else len(str(emb).strip("[]").split(","))
        if stored == expected:
            _ok(f"stored vectors are {stored}-dim")
        else:
            _fail(f"stored vectors are {stored}-dim but the current "
                  f"configuration produces {expected}-dim. The table needs "
                  f"re-ingesting, or the column and RPC need changing.")
            problems += 1

    # ── 3. Does the RPC accept a vector of the current width? ───────────────
    # match_document_chunks declares its argument as vector(N). If N drifted,
    # every retrieval fails at call time, not at deploy time.
    try:
        probe = embeddings.embed_texts(["rpc probe"])[0]
        client.rpc("match_document_chunks",
                   {"query_embedding": probe, "match_count": 1}).execute()
        _ok(f"match_document_chunks accepts a {expected}-dim vector")
    except Exception as exc:  # noqa: BLE001
        _fail(f"match_document_chunks rejected a {expected}-dim vector — its "
              f"signature is probably still the old width: {exc}")
        problems += 1

    print()
    if problems:
        print(f"{problems} problem(s). The database and the embedding "
              f"configuration are not in step.")
        return 1
    print("Database and embedding configuration agree.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
