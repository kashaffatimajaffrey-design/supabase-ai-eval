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
  target: string | null;
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

// Mean of the non-null values, or null when there are none.
function mean(values: (number | null)[]): number | null {
  const present = values.filter((v): v is number => v !== null);
  return present.length ? present.reduce((a, b) => a + b, 0) / present.length : null;
}

// Aggregate pass rate / avg scores per run, for the trend line.
// A query that errored writes no eval_results row, so results.length is the
// number of scored queries. A run with none scored has no pass rate at all:
// its metrics are null rather than 0, so the chart can leave it out instead of
// plotting a failure that never happened.
export async function fetchRunSummaries() {
  const runs = await fetchRuns();
  const summaries = await Promise.all(
    runs.map(async (run, index) => {
      const results = await fetchResultsForRun(run.id);
      const scored = results.length;
      const passRate = scored
        ? results.filter((r) => r.passed).length / scored
        : null;
      return {
        run,
        runNumber: index + 1,
        results,
        scored,
        passRate,
        avgRetrieval: mean(results.map((r) => r.retrieval_relevance)),
        avgAccuracy: mean(results.map((r) => r.answer_accuracy)),
        avgLatency: mean(results.map((r) => r.latency_ms)),
      };
    })
  );
  return summaries;
}
