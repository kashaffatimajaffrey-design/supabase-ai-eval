-- 0003_drop_any_ivfflat_index.sql
-- Run in the Supabase SQL editor.
--
-- Migration 0002 tried to remove the oversized ANN index with
--     drop index if exists document_chunks_embedding_idx;
-- and that was a silent no-op. document_chunks had been dropped and recreated
-- when the project moved from 1536-dim to 512-dim vectors, and the rebuilt
-- index did not come back under the name schema.sql originally gave it. The
-- "if exists" then swallowed the miss, the migration reported success, and the
-- index survived.
--
-- Measured after 0002 was applied: asking match_document_chunks for a chunk's
-- OWN stored embedding with match_count=5 returned between 1 and 4 rows for all
-- 12 chunks. A sequential scan over 12 rows returns 5 every time, so short
-- results prove an ANN index was still filtering. ivfflat with lists=100 over
-- 12 rows leaves almost every list empty, and ivfflat.probes defaults to 1, so
-- a query searches one mostly-empty cluster and silently loses most of the
-- corpus -- sometimes all of it.
--
-- Dropping by name is the bug. This drops by PROPERTY: any ivfflat index on
-- document_chunks, whatever it is called.

do $$
declare
  idx record;
  dropped int := 0;
begin
  for idx in
    select schemaname, indexname
    from pg_indexes
    where tablename = 'document_chunks'
      and indexdef ilike '%ivfflat%'
  loop
    execute format('drop index if exists %I.%I', idx.schemaname, idx.indexname);
    raise notice 'dropped ivfflat index: %.%', idx.schemaname, idx.indexname;
    dropped := dropped + 1;
  end loop;

  if dropped = 0 then
    raise notice 'no ivfflat index found on document_chunks (already clean)';
  end if;
end $$;

-- Verification. Expect zero rows: no ANN index should remain on this table at
-- this corpus size. Exact search over a few thousand rows is fast and, unlike
-- ivfflat, cannot silently drop results.
select indexname, indexdef
from pg_indexes
where tablename = 'document_chunks'
  and indexdef ilike '%ivfflat%';
