"""
retriever.py
Wraps the pgvector similarity search exposed via the `match_document_chunks`
Postgres function (see db/schema.sql), called through Supabase RPC.
"""
from embeddings import embed_query
from db_client import match_chunks


def retrieve(query: str, k: int = 5) -> list[dict]:
    """
    Returns a list of {id, document_id, content, similarity}, ordered by
    cosine similarity (highest first).
    """
    query_embedding = embed_query(query)
    return match_chunks(query_embedding, match_count=k)
