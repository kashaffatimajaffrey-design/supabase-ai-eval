"""
seed_eval_queries.py
Inserts ground-truth eval questions into the eval_queries table.
Questions are based on the sample_docs in this repo.

Usage:
    python seed_eval_queries.py
"""
from dotenv import load_dotenv
load_dotenv()

from db_client import get_supabase_client

QUERIES = [
    {
        "query": "How do I enable Row Level Security on a table?",
        "expected_answer": "Use ALTER TABLE table_name ENABLE ROW LEVEL SECURITY. Then create policies using CREATE POLICY.",
        "category": "rls",
        "difficulty": "easy",
    },
    {
        "query": "What is the difference between anon and service_role API keys?",
        "expected_answer": "anon key is for client-side use and respects RLS. service_role key bypasses RLS and is for server-side use only.",
        "category": "auth",
        "difficulty": "easy",
    },
    {
        "query": "How do I run a database migration using the Supabase CLI?",
        "expected_answer": "Use supabase db push to apply migrations, or supabase migration new to create a new migration file.",
        "category": "cli",
        "difficulty": "easy",
    },
    {
        "query": "How do I perform a vector similarity search using pgvector?",
        "expected_answer": "Use the <=> operator for cosine distance. Enable the vector extension first with CREATE EXTENSION vector.",
        "category": "pgvector",
        "difficulty": "medium",
    },
    {
        "query": "How do I deploy an Edge Function in Supabase?",
        "expected_answer": "Use supabase functions deploy function-name via the Supabase CLI.",
        "category": "edge-functions",
        "difficulty": "easy",
    },
    {
        "query": "How do I upload a file to Supabase Storage?",
        "expected_answer": "Use the supabase.storage.from('bucket-name').upload(path, file) method from the client library.",
        "category": "storage",
        "difficulty": "easy",
    },
    {
        "query": "What does the ivfflat index do in pgvector?",
        "expected_answer": "ivfflat is an approximate nearest neighbor index for vector columns that speeds up similarity search at the cost of some accuracy.",
        "category": "pgvector",
        "difficulty": "medium",
    },
    {
        "query": "Can Edge Functions access environment variables?",
        "expected_answer": "Yes, via Deno.env.get('VAR_NAME'). Secrets are set using supabase secrets set.",
        "category": "edge-functions",
        "difficulty": "medium",
    },
]


def seed():
    client = get_supabase_client()
    res = client.table("eval_queries").insert(QUERIES).execute()
    print(f"Seeded {len(res.data)} eval queries.")


if __name__ == "__main__":
    seed()