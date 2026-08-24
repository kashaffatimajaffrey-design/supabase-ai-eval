-- 0002_fix_retrieval_and_multi_target.sql
-- Run in the Supabase SQL editor.
--
-- Part A fixes three defects found by the 2026-08-24 eval run.
-- Part B generalises the harness so it can score systems other than the
-- Supabase-docs RAG (CEREBRO's /v1/analyze/news, Apollo-M's explain layer).

-- ==========================================================
-- A. Correctness fixes
-- ==========================================================

-- A1. ivfflat with lists=100 over a 12-row table caused nondeterministic
--     ZERO-row retrieval: ivfflat.probes defaults to 1, most of the 100 lists
--     are empty, so a query whose nearest centroid lands on an empty list gets
--     nothing back. At this size an exact scan is faster and always correct.
--     Reintroduce an ANN index only at scale (lists ~= rows/1000, then ANALYZE).
drop index if exists document_chunks_embedding_idx;

-- A2. documents had no unique key on source_url, so every ingest.py run
--     appended a duplicate corpus (6 files -> 25 rows). Duplicate chunks then
--     dominated top-k retrieval and drove retrieval_relevance toward zero.
alter table documents
  add constraint documents_source_url_key unique (source_url);

-- ==========================================================
-- B. Multi-target support
-- ==========================================================

-- B1. Which system under test a query belongs to. Existing rows are the
--     Supabase-docs RAG.
alter table eval_queries
  add column if not exists target text not null default 'supabase_docs';

alter table eval_runs
  add column if not exists target text not null default 'supabase_docs';

-- B2. Non-RAG targets have no chunk UUIDs to record. retrieved_chunk_ids stays
--     uuid[] for the docs RAG; evidence carries whatever the target actually
--     returned (CEREBRO source URLs, Apollo input metrics) so a result stays
--     auditable regardless of target.
alter table eval_results
  add column if not exists evidence jsonb;

-- B3. A3 (was: unique on query alone). The same question can legitimately be
--     asked of two different targets, so uniqueness is per (query, target).
--     This is what actually prevents the seeder duplication that turned 8
--     questions into 40 rows -- the Python-side guard is racy on its own.
alter table eval_queries
  add constraint eval_queries_query_target_key unique (query, target);
