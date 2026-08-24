# supabase-ai-eval

A RAG agent that answers Supabase docs questions, with every retrieval and 
generation quality metric logged back into Supabase itself. Built to 
demonstrate deep, hands-on familiarity with the Supabase stack — database, 
RLS, pgvector, Storage, and the JS/Python client libraries.

## Youtube Demo:

https://youtu.be/e-qrZo0g7us?si=lacN2cY8HtO5myBa

## Why I built this

I built this to go beyond tutorials. The only way to genuinely understand 
why a developer is confused about RLS, or why their vector search is slow, 
is to have hit those walls yourself. This project is the result of that — 
real debugging, real errors, real fixes.

## What it covers across the Supabase stack

| Supabase product | How it's used here |
|---|---|
| **Postgres + pgvector** | `document_chunks` with a `vector(512)` column, HNSW index, cosine similarity via RPC — plus hybrid retrieval fusing vector search with Postgres full-text |
| **Row Level Security** | All 5 tables have RLS enabled. Public read policies for the dashboard (anon key). Writes locked to service_role only |
| **Storage** | Covered in sample docs — ingested, chunked, and retrievable by the RAG agent |
| **Edge Functions** | Covered in sample docs — ingested, chunked, and retrievable by the RAG agent |
| **Auth** | API key handling — anon key for frontend (respects RLS), service_role for backend (bypasses RLS). Documented in sample docs |
| **PostgREST / RPC** | `match_document_chunks()` and `match_document_chunks_hybrid()` SQL functions called via `.rpc()` from Python |
| **React client** | Frontend reads `eval_runs` and `eval_results` via `@supabase/supabase-js` with anon key |
| **Observability** | Monitored via Supabase dashboard — query performance, peak connections, disk IO, service health |

## Architecture
sample_docs/*.md ──ingest.py──▶ documents + document_chunks (pgvector)

│

retriever.py (embed query → RPC match)

│

query ──▶ rag_agent.py ──▶ Claude ──▶ grounded answer

│

┌───────────────┴──────────────┐

│                               │

mcp_server.py                   run_eval.py

(MCP tool surface)          (LLM-as-judge scoring,

logs to eval_runs/results)

│

frontend/ (Vite + React)

live eval dashboard via

anon key + Supabase JS

## Database schema

Five tables, one RPC function — all in `db/schema.sql`:

- **`documents`** — raw source docs (url, title, full text)
- **`document_chunks`** — chunked text + `vector(512)` embedding, FK to `documents`, HNSW index,
  and a generated `content_fts` tsvector with a GIN index for the keyword half of hybrid search
- **`eval_queries`** — test set (question, expected answer, category, difficulty)
- **`eval_runs`** — one row per eval execution (model, embed model, git commit, timestamps)
- **`eval_results`** — per-query scores (retrieval_relevance, answer_accuracy, latency_ms, passed, judge_reasoning)
- **`match_document_chunks(query_embedding, match_count)`** — cosine distance ordering via RPC

RLS is enabled on all tables. Public `SELECT` policies allow the React 
dashboard to read with just the anon key. No public insert/update/delete — 
only service_role can write, used server-side by ingest and eval scripts.

## Retrieval: vector, keyword, or both

`retrieve()` is vector-only. `retrieve_hybrid()` fuses it with Postgres
full-text search using reciprocal rank fusion, and is worth reaching for when
queries carry exact identifiers.

Embeddings rank by meaning, so a rare literal token is diluted by the prose
around it and the chunk that actually contains it can fall below one that merely
discusses the topic. Measured on this corpus:

| Query | Vector only (top 3) | Hybrid (top 3) |
|---|---|---|
| "How do I stop other users from reading my rows?" | RLS, RLS, Auth Keys | same order, unchanged |
| `auth.uid()` | Auth Keys, Storage, Auth Keys | **RLS**, Storage, Auth Keys |

For `auth.uid()` the Row Level Security chunk ranks **5th by vector and 1st by
keyword**, so vector-only retrieval misses it entirely at k=3. On the
plain-language question the keyword half matches nothing and the vector ordering
carries through untouched — fusion helps where it can and stays out of the way
where it cannot.

Fusion is by rank, not by score. Cosine similarity is bounded 0..1 and `ts_rank`
is unbounded and corpus-dependent, so blending the numbers means inventing a
scale factor; using positions avoids the question.

## Guarding against schema drift

The embedding dimension is declared in three places that cannot check each
other: `EMBEDDING_DIMS`, the `vector(N)` column, and the RPC's argument type.
Changing provider means changing all three, and a mismatch fails quietly — the
write is rejected, the table stays empty, and retrieval returns nothing, which
looks like a bad model rather than a schema problem. This project spent time in
exactly that state.

```bash
python backend/check_schema_drift.py
```

Checks that the provider still returns the width `EMBEDDING_DIMS` claims, that
the vectors actually stored match it, and that the RPC accepts one. Exits
non-zero on any disagreement, so it can run in CI or before an ingest.

## Real errors I hit and fixed

This is the part that matters for support work — knowing what breaks and why:

- **`KeyError: SUPABASE_URL`** — `load_dotenv()` firing after `os.environ` 
  reads at module import time. Fixed by moving `load_dotenv()` to the top 
  of every entry point before any other imports.
- **`Invalid API key` (401)** — `supabase-py` rejected the new `sb_secret_`
  format keys, so the workaround at the time was the legacy JWT `service_role`
  key from Settings → API Keys → Legacy tab. **No longer needed**: re-tested on
  supabase-py 2.31.0 and an `sb_secret_` key authenticates and writes fine, so
  the current dashboard key works directly.
- **`vector(1536)` dimension mismatch** — switched from OpenAI 
  (`text-embedding-3-small`, 1536-dim) to Voyage AI (`voyage-3-lite`, 
  512-dim) mid-build. Had to drop and recreate `document_chunks` and update 
  the `match_document_chunks` RPC signature to `vector(512)`.
- **An ivfflat index silently destroying recall** — the sharpest one. With
  `lists=100` over a 12-row table and `ivfflat.probes` at its default of 1, a
  search reads a single list and returns only the rows that happen to live in
  it. Every query came back with one result at ~0.18 similarity from the wrong
  document, which reads like a weak embedding model, not an index problem.
  Dropping the index took the query "How do I enable Row Level Security on a
  table?" from 1 result at 0.18 to 5 results led by the Row Level Security
  chunk at 0.69. Replaced with HNSW, which has no list count to size against
  the row count and so cannot fail this way as the table grows.
- **Voyage rate limit (3 RPM free tier)** — added `time.sleep(20)` between 
  ingestion calls to stay within free tier limits.
- **MCP stdio corruption** — any `print()` firing during import corrupts the 
  JSON-RPC channel. Fixed by suppressing stdout during module imports in 
  `mcp_server.py`.
- **Anthropic + OpenAI billing** — both require paid credits for API access. 
  Eval runs show correct pipeline flow but 0% pass rate until credits are 
  added — documented honestly in the demo video.

## Project layout
supabase-ai-eval/

├── db/

│   ├── schema.sql              # pgvector schema, HNSW index, RPC fn, RLS policies

│   └── hybrid_search.sql       # tsvector column + RRF fusion RPC (run after schema.sql)

├── backend/

│   ├── db_client.py            # Supabase client (service_role, server-side)

│   ├── check_schema_drift.py   # fails if the DB and the embedding config disagree

│   ├── embeddings.py           # pluggable: OpenAI / Voyage AI

│   ├── retriever.py            # embed query → match_document_chunks RPC

│   ├── rag_agent.py            # retrieval + Claude generation

│   ├── ingest.py               # chunk + embed + insert docs

│   ├── mcp_server.py           # MCP tool surface

│   ├── run_eval.py             # orchestrates eval runs, logs to Supabase

│   └── seed_eval_queries.py    # seeds 8 test queries across categories

├── frontend/                   # Vite + React + Tailwind eval dashboard

│   └── src/{App.tsx, api.ts, main.tsx}

├── sample_docs/                # 6 local .md files (Auth, RLS, pgvector,

│                               #   Edge Functions, Storage, CLI Migrations)

├── .env.example                # backend env template

└── frontend/.env.example       # frontend env template (anon key only)

## Setup

```bash
# 1. backend
pip install -r requirements.txt
cp .env.example .env   # fill in Supabase + Anthropic + Voyage keys

# 2. apply schema (Supabase SQL editor)
#    enable the vector extension first: Database → Extensions → vector
#    paste db/schema.sql and run it
#    then paste db/hybrid_search.sql for keyword + RRF retrieval
#    both are idempotent, so re-running either is safe

# 3. ingest sample docs
cd backend && python ingest.py --dir ../sample_docs

# 4. run eval
python run_eval.py --label "baseline"

# 5. frontend
cd ../frontend && npm install
cp .env.example .env   # VITE_SUPABASE_URL + VITE_SUPABASE_ANON_KEY
npm run dev
```

## MCP integration

Register in Claude Desktop's config (`%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "supabase-docs": {
      "command": "C:\\path\\to\\.venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\backend\\mcp_server.py"]
    }
  }
}
```

Two tools exposed: `search_supabase_docs` (raw retrieval) and 
`ask_supabase_docs` (RAG answer with citations).

## What I'd build next

A natural extension is a support debugging agent — using `ask_supabase_docs` 
as one tool among several (live logs, schema introspection, RLS policy 
checks) so it can answer "why can't this user read this row" by reasoning 
over live project state, not just static docs. Directly useful for 
accelerating support triage.

## Stack

Python · FastMCP · supabase-py · Voyage AI · Anthropic Claude · 
React · Vite · Tailwind · Recharts · pgvector · PostgreSQL
