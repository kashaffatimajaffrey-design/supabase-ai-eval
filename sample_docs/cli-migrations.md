# Database migrations with the Supabase CLI

The Supabase CLI tracks schema changes as versioned SQL migration files,
so your database structure can live in version control alongside your
application code instead of being edited ad hoc through a dashboard.

Create a new migration:

```bash
supabase migration new add_eval_tables
```

This generates an empty, timestamped `.sql` file under
`supabase/migrations/`. Write your schema changes into it — creating
tables, adding columns, defining RLS policies, whatever the change is.

To apply migrations to your remote project:

```bash
supabase db push
```

To apply them to a local development database instead (useful for testing
before touching production):

```bash
supabase migration up
```

Because migrations are just SQL files, they're easy to review in a pull
request, easy to roll back by writing a follow-up migration, and easy to
replay from scratch when spinning up a new environment.
