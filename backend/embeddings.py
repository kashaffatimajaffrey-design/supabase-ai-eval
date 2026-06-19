"""
embeddings.py
Pluggable embedding provider so the project isn't locked to one vendor.
Default: OpenAI text-embedding-3-small (1536-dim, matches db/schema.sql).
Alternative: Voyage AI (Anthropic's recommended embedding partner) — set
EMBEDDING_PROVIDER=voyage and update the `vector(1536)` columns in
schema.sql to match Voyage's output dimension if you switch.
"""
import os

EMBEDDING_PROVIDER = os.environ.get("EMBEDDING_PROVIDER", "openai")
EMBEDDING_MODEL = os.environ.get(
    "EMBEDDING_MODEL",
    "text-embedding-3-small" if EMBEDDING_PROVIDER == "openai" else "voyage-3-lite",
)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts. Returns one vector per input text, same order."""
    if EMBEDDING_PROVIDER == "openai":
        from openai import OpenAI
        client = OpenAI()
        res = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
        return [d.embedding for d in res.data]

    if EMBEDDING_PROVIDER == "voyage":
        import voyageai
        client = voyageai.Client()
        res = client.embed(texts, model=EMBEDDING_MODEL, input_type="document")
        return res.embeddings

    raise ValueError(f"Unknown EMBEDDING_PROVIDER: {EMBEDDING_PROVIDER}")


def embed_query(text: str) -> list[float]:
    """Embed a single query string (some providers distinguish query vs document)."""
    if EMBEDDING_PROVIDER == "voyage":
        import voyageai
        client = voyageai.Client()
        res = client.embed([text], model=EMBEDDING_MODEL, input_type="query")
        return res.embeddings[0]
    return embed_texts([text])[0]
