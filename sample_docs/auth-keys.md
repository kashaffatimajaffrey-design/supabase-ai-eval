# API Keys: anon vs service_role

Every Supabase project ships two main API keys.

The **anon key** (anonymous key) is safe to expose in a browser or mobile
app. Requests made with it go through PostgREST as the `anon` Postgres role,
which means every query is still filtered through your Row Level Security
policies. A user can never see more than what your policies allow, no
matter what the client-side code does.

The **service_role key** bypasses Row Level Security entirely. It should
only ever be used in a trusted server-side environment — a backend, an
Edge Function, a cron job — and must never be shipped to a frontend bundle,
committed to a public repo, or embedded in a mobile app, since anyone who
obtains it has unrestricted read/write access to your entire database.

A common pattern: use the anon key in your frontend for normal user-scoped
requests, and reserve the service_role key for admin scripts, data
migrations, or backend jobs that legitimately need to read or write across
all rows regardless of ownership.
