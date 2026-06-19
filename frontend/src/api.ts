import { createClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as string;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string;

export const supabase = createClient(supabaseUrl, supabaseAnonKey);

export type EvalRun = {
  id: string;
  run_label: string | null;
  model_used: string | null;
  embed_model: string | null;
  git_commit: string | null;
  started_at: string;
  finished_at: string | null;
  notes: string | null;
};

export type EvalResult = {
  id: string;
  eval_run_id: string;
  eval_query_id: string;
  generated_answer: string | null;
  retrieval_relevance: number | null;
  answer_accuracy: number | null;
  latency_ms: number | null;
  passed: boolean | null;
  judge_reasoning: string | null;
  eval_queries?: { query: string; category: string | null; difficulty: string | null };
};

export async function fetchRuns(): Promise<EvalRun[]> {
  const { data, error } = await supabase
    .from("eval_runs")
    .select("*")
    .order("started_at", { ascending: true });
  if (error) throw error;
  return data ?? [];
}

export async function fetchResultsForRun(runId: string): Promise<EvalResult[]> {
  const { data, error } = await supabase
    .from("eval_results")
    .select("*, eval_queries(query, category, difficulty)")
    .eq("eval_run_id", runId);
  if (error) throw error;
  return data ?? [];
}

// Aggregate pass rate / avg scores per run, for the trend line.
export async function fetchRunSummaries() {
  const runs = await fetchRuns();
  const summaries = await Promise.all(
    runs.map(async (run) => {
      const results = await fetchResultsForRun(run.id);
      const n = results.length || 1;
      const passRate = results.filter((r) => r.passed).length / n;
      const avgRetrieval =
        results.reduce((s, r) => s + (r.retrieval_relevance ?? 0), 0) / n;
      const avgAccuracy =
        results.reduce((s, r) => s + (r.answer_accuracy ?? 0), 0) / n;
      const avgLatency =
        results.reduce((s, r) => s + (r.latency_ms ?? 0), 0) / n;
      return {
        run,
        results,
        passRate,
        avgRetrieval,
        avgAccuracy,
        avgLatency,
      };
    })
  );
  return summaries;
}
