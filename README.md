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
| **Postgres + pgvector** | `document_chunks` table with `vector(512)` column, ivfflat index, cosine similarity search via RPC |
| **Row Level Security** | All 5 tables have RLS enabled. Public read policies for the dashboard (anon key). Writes locked to service_role only |
| **Storage** | Covered in sample docs — ingested, chunked, and retrievable by the RAG agent |
| **Edge Functions** | Covered in sample docs — ingested, chunked, and retrievable by the RAG agent |
| **Auth** | API key handling — anon key for frontend (respects RLS), service_role for backend (bypasses RLS). Documented in sample docs |
| **PostgREST / RPC** | `match_document_chunks()` SQL function called via `.rpc()` from Python |
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
- **`document_chunks`** — chunked text + `vector(512)` embedding, FK to `documents`, ivfflat index
- **`eval_queries`** — test set (question, expected answer, category, difficulty)
- **`eval_runs`** — one row per eval execution (model, embed model, git commit, timestamps)
- **`eval_results`** — per-query scores (retrieval_relevance, answer_accuracy, latency_ms, passed, judge_reasoning)
- **`match_document_chunks(query_embedding, match_count)`** — cosine distance ordering via RPC

RLS is enabled on all tables. Public `SELECT` policies allow the React 
dashboard to read with just the anon key. No public insert/update/delete — 
only service_role can write, used server-side by ingest and eval scripts.

## Real errors I hit and fixed

This is the part that matters for support work — knowing what breaks and why:

- **`KeyError: SUPABASE_URL`** — `load_dotenv()` firing after `os.environ` 
  reads at module import time. Fixed by moving `load_dotenv()` to the top 
  of every entry point before any other imports.
- **`Invalid API key` (401)** — `supabase-py` doesn't accept the new 
  `sb_secret_` format keys yet. Fix: use the legacy JWT `service_role` key 
  from Settings → API Keys → Legacy tab.
- **`vector(1536)` dimension mismatch** — switched from OpenAI 
  (`text-embedding-3-small`, 1536-dim) to Voyage AI (`voyage-3-lite`, 
  512-dim) mid-build. Had to drop and recreate `document_chunks` and update 
  the `match_document_chunks` RPC signature to `vector(512)`.
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

│   └── schema.sql              # pgvector schema, RPC fn, RLS policies

├── backend/

│   ├── db_client.py            # Supabase client (service_role, server-side)

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
#    paste db/schema.sql and run it
#    enable the vector extension first: Database → Extensions → vector

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
