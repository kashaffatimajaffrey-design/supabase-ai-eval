# Storage

Supabase Storage handles large file uploads — images, videos, documents —
outside of your regular Postgres tables, while still integrating with the
rest of Supabase.

Files live in buckets, which can be public (readable by anyone with the
URL) or private (access controlled by policy). Under the hood, every
object's metadata is a row in the `storage.objects` table, which means
Row Level Security applies to Storage exactly the way it applies to any
other table.

A policy restricting uploads to a user's own folder might look like:

```sql
create policy "users can upload to their own folder"
  on storage.objects for insert
  with check (
    bucket_id = 'avatars'
    and (storage.foldername(name))[1] = auth.uid()::text
  );
```

This is a common point of confusion: people assume Storage has its own
separate permission system, but it's the same RLS engine used everywhere
else in Supabase, just applied to a different table.
