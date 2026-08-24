"""Target: the Supabase-docs RAG in this repo (the original system under test)."""
from __future__ import annotations

from rag_agent import answer_query

from .base import TargetResponse


class SupabaseDocsTarget:
    NAME = "supabase_docs"
    RUBRIC = """1. retrieval_relevance: Did the retrieved chunks contain the information needed to answer the question?
2. answer_accuracy: Does the generated answer correctly address the question based on the expected facts?"""

    def answer(self, query: str, expected: str, k: int) -> TargetResponse:
        r = answer_query(query, k=k)
        return TargetResponse(
            answer=r["answer"],
            latency_ms=r["latency_ms"],
            retrieved_chunk_ids=r["retrieved_chunk_ids"],
            context=[c["content"] for c in r["retrieved_chunks"]],
            evidence={"chunk_count": len(r["retrieved_chunks"])},
        )
