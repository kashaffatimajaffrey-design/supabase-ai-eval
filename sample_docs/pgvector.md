# Vector embeddings with pgvector

Supabase ships the `pgvector` Postgres extension, which lets you store and
query vector embeddings directly in your existing database instead of
running a separate vector store.

Enable it once per project:

```sql
create extension if not exists vector;
```

Add a vector column whose dimension matches your embedding model's output
(1536 for OpenAI's text-embedding-3-small, for example):

```sql
create table document_chunks (
  id uuid primary key default gen_random_uuid(),
  content text,
  embedding vector(1536)
);
```

Query for nearest neighbors using a distance operator — `<=>` for cosine
distance, `<->` for Euclidean (L2), `<#>` for inner product:

```sql
select content
from document_chunks
order by embedding <=> '[0.01, 0.02, ...]'::vector
limit 5;
```

On a sequential scan this works but gets slow as the table grows. For
approximate nearest neighbor search at scale, add an index — `ivfflat` or
`hnsw` — on the embedding column:

```sql
create index on document_chunks
  using ivfflat (embedding vector_cosine_ops) with (lists = 100);
```

This trades a small amount of recall for a large speedup, which is the
right tradeoff for most retrieval-augmented generation (RAG) workloads.
You can also wrap the similarity query in a Postgres function and expose
it as an RPC endpoint, so client code (or an MCP server) can call it
without writing raw SQL.
