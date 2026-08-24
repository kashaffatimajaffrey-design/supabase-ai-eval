-- supabase-ai-eval: database schema
-- Run this in the Supabase SQL editor, or via `supabase db push`.

create extension if not exists vector;
create extension if not exists pgcrypto; -- for gen_random_uuid()

-- ============================================================
-- 1. SOURCE DOCS
-- ============================================================

create table if not exists documents (
  id            uuid primary key default gen_random_uuid(),
  source_url    text not null,
  title         text,
  raw_content   text not null,
  fetched_at    timestamptz not null default now()
);

create table if not exists document_chunks (
  id            uuid primary key default gen_random_uuid(),
  document_id   uuid not null references documents(id) on delete cascade,
  chunk_index   int not null,
  content       text not null,
  token_count   int,
  embedding     vector(512), -- must match embeddings.EMBEDDING_DIMS (voyage-3-lite = 512)
  created_at    timestamptz not null default now()
);

-- ── ANN index ───────────────────────────────────────────────────────────────
-- HNSW, not ivfflat, and the difference is not academic. An ivfflat index built
-- with lists=100 over a small table silently destroys recall: the rows are
-- spread across 100 lists, ivfflat.probes defaults to 1, so a search reads one
-- list and returns whatever few rows happen to live in it. This project ran in
-- exactly that state — 12 chunks, every query returning a single result at
-- ~0.18 similarity from the wrong document, which reads like a bad embedding
-- model rather than an index misconfiguration. Dropping it took the same query
-- from 1 result at 0.18 to 5 results led by the correct document at 0.69.
--
-- HNSW has no equivalent cliff. It needs no list count tuned to the row count,
-- so it behaves correctly at 12 rows and at 12 million, and it cannot quietly
-- start under-returning as the table grows away from whatever `lists` was
-- guessed at build time.
drop index if exists document_chunks_embedding_idx;  -- legacy ivfflat, see above

create index if not exists document_chunks_embedding_hnsw
  on document_chunks using hnsw (embedding vector_cosine_ops)
  with (m = 16, ef_construction = 64);

create index if not exists document_chunks_document_id_idx
  on document_chunks (document_id);

-- ============================================================
-- 2. EVAL SET (the "ground truth" test queries)
-- ============================================================

create table if not exists eval_queries (
  id               uuid primary key default gen_random_uuid(),
  query            text not null,
  expected_answer  text not null,   -- reference facts the answer should contain
  category         text,            -- e.g. 'rls', 'pgvector', 'edge-functions', 'auth'
  difficulty       text,            -- 'easy' | 'medium' | 'hard'
  created_at       timestamptz not null default now()
);

-- ============================================================
-- 3. EVAL RUNS + RESULTS (this is the "eval-first" core of the project)
-- ============================================================

create table if not exists eval_runs (
  id            uuid primary key default gen_random_uuid(),
  run_label     text,                -- e.g. 'chunk_size=500 / k=5'
  model_used    text,                -- generation model
  embed_model   text,                -- embedding model
  git_commit    text,
  started_at    timestamptz not null default now(),
  finished_at   timestamptz,
  notes         text
);

create table if not exists eval_results (
  id                       uuid primary key default gen_random_uuid(),
  eval_run_id              uuid not null references eval_runs(id) on delete cascade,
  eval_query_id            uuid not null references eval_queries(id) on delete cascade,
  retrieved_chunk_ids      uuid[],
  generated_answer         text,
  retrieval_relevance      numeric,  -- 0.0–1.0, did retrieval surface the right chunks
  answer_accuracy          numeric,  -- 0.0–1.0, does the answer match expected facts
  latency_ms               int,
  passed                   boolean,  -- accuracy >= threshold (see run_eval.py)
  judge_reasoning          text,     -- why the LLM judge scored it this way
  created_at               timestamptz not null default now()
);

create index if not exists eval_results_run_idx on eval_results (eval_run_id);

-- ============================================================
-- 4. RETRIEVAL FUNCTION (called via Supabase RPC from retriever.py)
-- ============================================================

create or replace function match_document_chunks(
  query_embedding vector(512),
  match_count     int default 5
)
returns table (
  id           uuid,
  document_id  uuid,
  content      text,
  similarity   float
)
language sql stable
as $$
  select
    document_chunks.id,
    document_chunks.document_id,
    document_chunks.content,
    1 - (document_chunks.embedding <=> query_embedding) as similarity
  from document_chunks
  order by document_chunks.embedding <=> query_embedding
  limit match_count;
$$;

-- ============================================================
-- 5. RLS — read-only public access for the eval dashboard,
--    writes only via service_role (used by ingest/eval scripts)
-- ============================================================

alter table documents enable row level security;
alter table document_chunks enable row level security;
alter table eval_queries enable row level security;
alter table eval_runs enable row level security;
alter table eval_results enable row level security;

create policy "public read documents" on documents for select using (true);
create policy "public read chunks" on document_chunks for select using (true);
create policy "public read eval_queries" on eval_queries for select using (true);
create policy "public read eval_runs" on eval_runs for select using (true);
create policy "public read eval_results" on eval_results for select using (true);
-- No insert/update/delete policies for anon/authenticated -> only service_role (bypasses RLS) can write.
