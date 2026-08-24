"""
embeddings.py
Pluggable embedding provider so the project isn't locked to one vendor.

Providers are selected with EMBEDDING_PROVIDER:
  openai  - text-embedding-3-small (1536-dim)
  voyage  - voyage-3-lite (512-dim)

NOTE: the vector dimension is provider-specific and must match the `vector(N)`
columns in db/schema.sql. EMBEDDING_DIMS below is the single source of truth;
assert_dimension() lets callers fail loudly at ingest time instead of getting a
confusing PostgREST error.

Voyage's unpaid tier allows 3 requests/minute. Rather than scattering
time.sleep() calls through every caller, pacing and retry live here so ingest
and the eval harness both get them for free.
"""
import os
import time

import config  # noqa: F401 - loads the repo-root .env

EMBEDDING_PROVIDER = os.environ.get("EMBEDDING_PROVIDER", "openai")
EMBEDDING_MODEL = os.environ.get(
    "EMBEDDING_MODEL",
    "text-embedding-3-small" if EMBEDDING_PROVIDER == "openai" else "voyage-3-lite",
)

# Provider/model -> output dimension. Keep in sync with db/schema.sql.
EMBEDDING_DIMS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "voyage-3-lite": 512,
    "voyage-3": 1024,
}

# Seconds between Voyage calls. Unpaid tier = 3 RPM, so 21s keeps us just
# inside it. Set VOYAGE_MIN_INTERVAL_S=0 once a payment method is on file.
VOYAGE_MIN_INTERVAL = float(os.environ.get("VOYAGE_MIN_INTERVAL_S", "21"))
_MAX_RETRIES = 4

_last_call_at = 0.0


def expected_dimension() -> int | None:
    """Vector length this configuration produces, or None if the model is unknown."""
    return EMBEDDING_DIMS.get(EMBEDDING_MODEL)


def assert_dimension(vectors: list[list[float]]) -> None:
    """Fail loudly on a provider/schema dimension mismatch."""
    expected = expected_dimension()
    if not vectors or expected is None:
        return
    actual = len(vectors[0])
    if actual != expected:
        raise ValueError(
            f"{EMBEDDING_MODEL} returned {actual}-dim vectors but "
            f"EMBEDDING_DIMS says {expected}. Update EMBEDDING_DIMS and the "
            f"vector(N) columns in db/schema.sql before ingesting."
        )


def _is_rate_limit(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "rate limit" in text
        or "429" in text
        or "reduced rate limits" in text
        or "too many requests" in text
    )


def _paced(fn, *args, **kwargs):
    """Call fn, spacing Voyage requests out and retrying rate limits."""
    global _last_call_at
    if VOYAGE_MIN_INTERVAL <= 0:
        return fn(*args, **kwargs)

    for attempt in range(_MAX_RETRIES + 1):
        wait = VOYAGE_MIN_INTERVAL - (time.monotonic() - _last_call_at)
        if wait > 0:
            time.sleep(wait)
        try:
            result = fn(*args, **kwargs)
            _last_call_at = time.monotonic()
            return result
        except Exception as exc:
            _last_call_at = time.monotonic()
            if attempt == _MAX_RETRIES or not _is_rate_limit(exc):
                raise
            backoff = VOYAGE_MIN_INTERVAL * (2 ** attempt)
            print(f"    [embeddings] rate limited; retrying in {backoff:.0f}s "
                  f"(attempt {attempt + 1}/{_MAX_RETRIES})")
            time.sleep(backoff)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts. Returns one vector per input text, same order."""
    if EMBEDDING_PROVIDER == "openai":
        from openai import OpenAI
        client = OpenAI()
        res = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
        vectors = [d.embedding for d in res.data]

    elif EMBEDDING_PROVIDER == "voyage":
        import voyageai
        client = voyageai.Client()
        res = _paced(client.embed, texts, model=EMBEDDING_MODEL, input_type="document")
        vectors = res.embeddings

    else:
        raise ValueError(f"Unknown EMBEDDING_PROVIDER: {EMBEDDING_PROVIDER}")

    assert_dimension(vectors)
    return vectors


def embed_query(text: str) -> list[float]:
    """Embed a single query string (some providers distinguish query vs document)."""
    if EMBEDDING_PROVIDER == "voyage":
        import voyageai
        client = voyageai.Client()
        res = _paced(client.embed, [text], model=EMBEDDING_MODEL, input_type="query")
        assert_dimension(res.embeddings)
        return res.embeddings[0]
    return embed_texts([text])[0]
