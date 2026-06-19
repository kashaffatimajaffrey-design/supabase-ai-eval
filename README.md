# supabase-ai-eval

An eval-first RAG agent over the Supabase docs, exposed via MCP, with every
quality metric logged back into Supabase itself. Built as a portfolio piece
for Supabase's **AI Tooling Engineer** role.

The thesis: don't just build a chatbot that answers Supabase questions —
build the *instrumentation* that proves it's actually getting better (or
catches when it regresses), using Supabase as both the vector store and the
evals database.

## How it fits the role

| JD requirement | Where it lives here |
|---|---|
| MCP, agent skills, AI-developer surfaces | `backend/mcp_server.py` — exposes `search_supabase_docs` and `ask_supabase_docs` as MCP tools |
| Eval-first approach, instrumentation, feedback loops | `backend/eval/` — LLM-as-judge scoring, logged per-run to `eval_runs` / `eval_results` |
| Postgres + pgvector / embeddings | `db/schema.sql`, `backend/embeddings.py`, `backend/retriever.py` |
| Battle-tested, benchmarked tools | `run_eval.py` re-runs the full eval set on demand — change chunk size or k and compare pass rate run over run |
| How docs get exposed to agents | `backend/ingest.py` — chunking + embedding strategy is intentionally simple and documented, not a black box |

## Architecture

```
sample_docs/*.md  ──ingest.py──▶  documents + document_chunks (pgvector)
                                          │
                                   retriever.py (embed query → RPC match)
                                          │
query ──▶ rag_agent.py ──▶ Claude ──▶ grounded answer
                                          │
                          ┌───────────────┴────────────────┐
                          │                                  │
                  mcp_server.py                      eval/run_eval.py
              (exposes as MCP tools)              (scores via judge.py,
                                                    logs to eval_runs/results)
                                                            │
                                                  frontend/ (Vite + React)
                                                  reads eval_* tables via
                                                  anon key, renders dashboard
```

## Project layout

```
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
│   └── eval/
│       ├── eval_queries.json   # 8 seed queries across rls/pgvector/auth/etc.
│       ├── judge.py            # LLM-as-judge: retrieval_relevance + answer_accuracy
│       └── run_eval.py         # orchestrates a full eval run, logs to Supabase
├── frontend/                   # Vite + React + Tailwind eval dashboard
│   └── src/{App.tsx, api.ts, main.tsx}
├── sample_docs/                # 6 local .md files for ingesting without network access
├── requirements.txt
├── .env.example                 # backend secrets (service_role, API keys)
└── frontend/.env.example        # frontend secrets (anon key only)
```

**File count:** 30 files across 6 folders (`db/`, `backend/`, `backend/eval/`, `frontend/`, `frontend/src/`, `sample_docs/`) — 6 backend Python files + 3 eval files, 1 SQL schema, 9 frontend files (config + source), 6 sample docs, 2 env templates (root + frontend), plus this README.

## Database schema

Five tables, one RPC function:

- **`documents`** — raw source docs (url, title, full text)
- **`document_chunks`** — chunked text + `vector(1536)` embedding, FK to `documents`, ivfflat index for fast similarity search
- **`eval_queries`** — the test set (question, expected answer, category, difficulty)
- **`eval_runs`** — one row per eval execution (model used, embed model, git commit, timestamps)
- **`eval_results`** — per-query scores for a given run (retrieval_relevance, answer_accuracy, latency_ms, passed, judge_reasoning), FK to both `eval_runs` and `eval_queries`
- **`match_document_chunks(query_embedding, match_count)`** — SQL function doing the cosine-distance ordering, called via RPC from `retriever.py`

RLS: public read on everything (so the dashboard works with just the anon
key), no public write policies — only the `service_role` key (used
server-side by ingest/eval scripts) can insert.

## Setup

```bash
# 1. backend
pip install -r requirements.txt --break-system-packages
cp .env.example .env   # fill in Supabase + Anthropic + OpenAI keys

# 2. apply schema (Supabase SQL editor, or supabase CLI)
#    paste the contents of db/schema.sql and run it

# 3. ingest the sample docs
cd backend && python ingest.py --dir ../sample_docs

# 4. run an eval
python eval/run_eval.py --label "baseline"

# 5. frontend dashboard
cd ../frontend
npm install
cp .env.example .env   # fill in SUPABASE_URL + anon key (public, safe)
npm run dev
```

To use it as an MCP tool in Claude Desktop, point its config at
`backend/mcp_server.py` (see the docstring at the top of that file).

## What I'd build next

Given more time, the natural extension is feeding this same eval loop into
something like a dashboard debugging assistant — using `ask_supabase_docs`
as one tool among several (logs, schema introspection, RLS policy checks)
so an agent can answer "why is my query slow" or "why can't this user read
this row" by reasoning over live project state, not just static docs, with
the same eval-first discipline applied to grade *that* agent's answers too.

## Notes on scope

This was built as a focused, demoable proof of the eval-first pattern, not
a production system — chunking is paragraph-based and dependency-free
rather than using a tokenizer-aware splitter, the eval set is 8 queries
rather than hundreds, and there's no CI wiring yet. All three are
straightforward to extend; kept minimal here so the core idea (retrieval
and generation quality, measured and logged separately, over time) stays
legible.
