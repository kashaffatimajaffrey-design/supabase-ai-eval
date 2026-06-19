"""
rag_agent.py
The core "ask Supabase docs" loop: retrieve relevant chunks, ground a
Claude completion in them, and return both the answer and what was
retrieved (needed for the eval harness to score retrieval separately
from generation).
"""
import os
import time
from anthropic import Anthropic
from retriever import retrieve

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

SYSTEM_PROMPT = """You are a documentation assistant for Supabase. Answer the \
user's question using ONLY the provided context chunks from the Supabase docs. \
If the context doesn't contain the answer, say so plainly instead of guessing. \
Be concise and technically precise. Cite which chunk(s) you used by their index, \
like [1], [2]."""


def build_context_block(chunks: list[dict]) -> str:
    parts = []
    for i, c in enumerate(chunks, start=1):
        parts.append(f"[{i}] {c['content']}")
    return "\n\n".join(parts)


def answer_query(query: str, k: int = 5) -> dict:
    start = time.time()
    chunks = retrieve(query, k=k)
    context = build_context_block(chunks)

    client = Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=600,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Context:\n{context}\n\nQuestion: {query}",
            }
        ],
    )
    answer_text = "".join(
        block.text for block in response.content if block.type == "text"
    )
    latency_ms = int((time.time() - start) * 1000)

    return {
        "query": query,
        "answer": answer_text,
        "retrieved_chunk_ids": [c["id"] for c in chunks],
        "retrieved_chunks": chunks,
        "latency_ms": latency_ms,
    }


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "How do I enable Row Level Security?"
    result = answer_query(q)
    print(f"Q: {q}\n")
    print(result["answer"])
    print(f"\n({result['latency_ms']}ms, {len(result['retrieved_chunks'])} chunks)")
