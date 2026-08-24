"""
db_client.py
Thin wrapper around the Supabase Python client. Uses the service_role key
(server-side only — never ship this key to the frontend) so that ingest
and eval scripts can bypass RLS for writes.
"""
import os
import config  # noqa: F401 - loads the repo-root .env
from datetime import datetime, timezone
from functools import lru_cache
from supabase import create_client, Client


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    url = os.environ["SUPABASE_URL"]
    service_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, service_key)


def insert_document(source_url: str, title: str, raw_content: str) -> str:
    client = get_supabase_client()
    res = client.table("documents").insert({
        "source_url": source_url,
        "title": title,
        "raw_content": raw_content,
    }).execute()
    return res.data[0]["id"]


def insert_chunks(rows: list[dict]) -> None:
    """rows: list of {document_id, chunk_index, content, token_count, embedding}"""
    client = get_supabase_client()
    # Supabase/PostgREST batches well in groups of ~100
    for i in range(0, len(rows), 100):
        client.table("document_chunks").insert(rows[i:i + 100]).execute()


def match_chunks(query_embedding: list[float], match_count: int = 5) -> list[dict]:
    client = get_supabase_client()
    res = client.rpc("match_document_chunks", {
        "query_embedding": query_embedding,
        "match_count": match_count,
    }).execute()
    return res.data


def match_chunks_hybrid(query_embedding: list[float], query_text: str,
                        match_count: int = 5) -> list[dict]:
    """
    Vector and full-text retrieval fused by reciprocal rank (db/hybrid_search.sql).

    Returns the same keys as match_chunks plus vector_rank, keyword_rank and
    rrf_score, so a caller can see which half found a result rather than
    treating retrieval as a black box.
    """
    client = get_supabase_client()
    res = client.rpc("match_document_chunks_hybrid", {
        "query_embedding": query_embedding,
        "query_text": query_text,
        "match_count": match_count,
    }).execute()
    return res.data


def create_eval_run(run_label: str, model_used: str, embed_model: str, git_commit: str = "") -> str:
    client = get_supabase_client()
    res = client.table("eval_runs").insert({
        "run_label": run_label,
        "model_used": model_used,
        "embed_model": embed_model,
        "git_commit": git_commit,
    }).execute()
    return res.data[0]["id"]


def finish_eval_run(run_id: str, notes: str = "") -> None:
    client = get_supabase_client()
    client.table("eval_runs").update({
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "notes": notes,
    }).eq("id", run_id).execute()


def insert_eval_result(row: dict) -> None:
    client = get_supabase_client()
    client.table("eval_results").insert(row).execute()


def get_eval_queries() -> list[dict]:
    client = get_supabase_client()
    res = client.table("eval_queries").select("*").execute()
    return res.data


def replace_document(source_url: str, title: str, raw_content: str) -> str:
    """Insert a document, replacing any existing one with the same source_url.

    ingest.py originally called insert_document() unconditionally, so every
    re-run appended another copy of the whole corpus -- 6 source files had
    become 25 document rows. Duplicate chunks then dominated top-k retrieval
    (five copies of one chunk instead of five distinct ones), which silently
    drove eval retrieval_relevance to zero.

    document_chunks has ON DELETE CASCADE, so removing the old row clears its
    stale chunks too.
    """
    client = get_supabase_client()
    client.table("documents").delete().eq("source_url", source_url).execute()
    res = client.table("documents").insert({
        "source_url": source_url,
        "title": title,
        "raw_content": raw_content,
    }).execute()
    return res.data[0]["id"]
