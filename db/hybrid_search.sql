-- supabase-ai-eval: hybrid retrieval (vector + full-text)
--
-- Run after db/schema.sql. Idempotent — safe to re-run.
--
-- Why add keyword search to a vector store
-- ----------------------------------------
-- Embeddings match meaning, which is what you want for "how do I stop other
-- users reading my rows" finding the RLS document. They are weakest on exactly
-- the tokens documentation is full of: `auth.uid()`, `service_role`,
-- `vector_cosine_ops`, error codes like 42501. Those are rare strings whose
-- embedding is dominated by surrounding prose, so the chunk that literally
-- contains the answer can rank below one that merely discusses the topic.
--
-- Postgres already has the other half — full-text search — in the same
-- database, over the same rows, inside the same query. Using it costs one
-- generated column and a GIN index.
--
-- Fusion, not weighting
-- ---------------------
-- The two halves produce incomparable numbers: cosine similarity is 0..1,
-- ts_rank is unbounded and corpus-dependent. Normalising them against each
-- other means picking a scale factor that is really a guess. Reciprocal Rank
-- Fusion avoids the question by discarding the scores and using only the
-- positions, so a chunk ranked first by either method scores well regardless of
-- how the two systems happen to number things.

-- ── Full-text column ────────────────────────────────────────────────────────
-- Generated and stored, so it cannot drift from `content` the way a trigger-
-- maintained column can when someone updates a row by another path.
alter table document_chunks
  add column if not exists content_fts tsvector
  generated always as (to_tsvector('english', content)) stored;

create index if not exists document_chunks_content_fts_idx
  on document_chunks using gin (content_fts);

-- ── Hybrid retrieval ────────────────────────────────────────────────────────
-- Returns the same shape as match_document_chunks plus the two component ranks,
-- so the eval harness can attribute a result to the half that found it rather than
-- treating retrieval as a black box.
create or replace function match_document_chunks_hybrid(
  query_embedding vector(512),
  query_text      text,
  match_count     int default 5,
  rrf_k           int default 60
)
returns table (
  id            uuid,
  document_id   uuid,
  content       text,
  similarity    float,
  vector_rank   int,
  keyword_rank  int,
  rrf_score     float
)
language sql stable
as $$
  with semantic as (
    select
      dc.id,
      row_number() over (order by dc.embedding <=> query_embedding) as rank,
      1 - (dc.embedding <=> query_embedding) as similarity
    from document_chunks dc
    -- Deliberately wider than match_count: a chunk that is fourth by vector and
    -- first by keyword should still be reachable by the fusion below, and it
    -- would not be if each half were truncated to the final count first.
    order by dc.embedding <=> query_embedding
    limit greatest(match_count * 4, 20)
  ),
  keyword as (
    select
      dc.id,
      row_number() over (
        order by ts_rank_cd(dc.content_fts, websearch_to_tsquery('english', query_text)) desc
      ) as rank
    from document_chunks dc
    where dc.content_fts @@ websearch_to_tsquery('english', query_text)
    order by ts_rank_cd(dc.content_fts, websearch_to_tsquery('english', query_text)) desc
    limit greatest(match_count * 4, 20)
  )
  select
    dc.id,
    dc.document_id,
    dc.content,
    coalesce(s.similarity, 1 - (dc.embedding <=> query_embedding)) as similarity,
    s.rank::int as vector_rank,
    k.rank::int as keyword_rank,
    -- A row missing from one side contributes nothing from it rather than being
    -- penalised, which is what lets a strong keyword-only hit still surface.
    coalesce(1.0 / (rrf_k + s.rank), 0.0)
      + coalesce(1.0 / (rrf_k + k.rank), 0.0) as rrf_score
  from document_chunks dc
  left join semantic s on s.id = dc.id
  left join keyword  k on k.id = dc.id
  where s.id is not null or k.id is not null
  order by rrf_score desc
  limit match_count;
$$;
