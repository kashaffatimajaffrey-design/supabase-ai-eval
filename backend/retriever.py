"""
retriever.py
Wraps the pgvector similarity search exposed via the `match_document_chunks`
Postgres function (see db/schema.sql), called through Supabase RPC.
"""
from embeddings import embed_query
from db_client import match_chunks, match_chunks_hybrid


def retrieve(query: str, k: int = 5) -> list[dict]:
    """
    Returns a list of {id, document_id, content, similarity}, ordered by
    cosine similarity (highest first).
    """
    query_embedding = embed_query(query)
    return match_chunks(query_embedding, match_count=k)


def retrieve_hybrid(query: str, k: int = 5) -> list[dict]:
    """
    Same as retrieve(), but fuses vector similarity with Postgres full-text
    search before ranking.

    Worth using when queries contain exact identifiers. Embeddings rank by
    meaning, so a rare literal token — `auth.uid()`, `service_role`, an error
    code — is diluted by the prose around it, and the chunk that actually
    contains it can fall below one that merely discusses the topic. Measured on
    this corpus: the query "auth.uid()" ranks the Row Level Security chunk 5th
    by vector and 1st by keyword, so vector-only retrieval misses it at k=3 and
    hybrid returns it first.

    Plain-language questions are unaffected — on those the keyword half matches
    nothing and the vector ordering carries through unchanged.
    """
    return match_chunks_hybrid(embed_query(query), query, match_count=k)
