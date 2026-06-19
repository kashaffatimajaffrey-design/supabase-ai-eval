# Edge Functions

Edge Functions are server-side TypeScript functions, built on Deno, that
run close to your users on a global edge network rather than in a single
region. They're invoked over HTTPS, much like a typical backend API route,
but with a few key differences from a traditional server.

There's no server to provision or manage — you write a function, deploy it
with the Supabase CLI, and it scales automatically with traffic. Cold
starts are minimal since Deno's isolate model is lightweight compared to a
traditional container-based runtime.

A minimal function looks like:

```ts
Deno.serve(async (req) => {
  const { name } = await req.json();
  return new Response(`Hello ${name}`, {
    headers: { "Content-Type": "text/plain" },
  });
});
```

Deploy with:

```bash
supabase functions deploy hello-world
```

Edge Functions are commonly used for logic that needs the service_role key
(since it should never touch the client), for webhooks, for calling
third-party APIs with secrets that shouldn't be exposed in the frontend,
and for things like the RAG agent in this project — embedding a query and
calling an LLM server-side, then returning just the final answer to the
client.
