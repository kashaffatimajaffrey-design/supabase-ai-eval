# Row Level Security

Row Level Security (RLS) lets you control which rows a user can read, insert,
update, or delete in a Postgres table, enforced directly by the database
rather than in application code.

To enable it on a table:

```sql
alter table profiles enable row level security;
```

Once enabled, all access is denied by default until you add policies. A
policy defines who can do what:

```sql
create policy "users can read their own profile"
  on profiles for select
  using (auth.uid() = id);
```

You can write separate policies for select, insert, update, and delete, and
combine multiple policies on the same table — Postgres evaluates them with
OR logic for permissive policies. If you enable RLS but never add a policy,
the table becomes completely inaccessible through the API (the anon and
authenticated roles see zero rows), though the service_role key still
bypasses RLS entirely since it's meant for trusted server-side use.

RLS also applies to Supabase Storage: the storage.objects table is a regular
Postgres table under the hood, so you can write RLS policies to control
who can upload, read, or delete files in a bucket using the same
`create policy` syntax.
