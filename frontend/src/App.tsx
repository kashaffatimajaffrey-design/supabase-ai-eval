import { useEffect, useState } from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import { fetchRunSummaries, EvalResult } from "./api";

type Summary = Awaited<ReturnType<typeof fetchRunSummaries>>[number];

function pct(n: number | null) {
  return n === null ? "—" : `${Math.round(n * 100)}%`;
}

function toPercent(n: number | null) {
  return n === null ? null : Math.round(n * 100);
}

type TrendPoint = {
  run: string;
  label: string;
  startedAt: string;
  scored: number;
  passRate: number | null;
  accuracy: number | null;
};

// The x-axis only has room for "#7"; the run label, date and sample size live
// here so a 1-query smoke test can't be mistaken for a full run.
function TrendTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { payload: TrendPoint }[];
}) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="max-w-xs rounded border border-panelBorder bg-panel px-3 py-2 font-mono text-xs text-ink1">
      <div className="text-ink2">
        {p.run} · {new Date(p.startedAt).toLocaleDateString()}
      </div>
      <div className="mt-1 whitespace-normal">{p.label}</div>
      <div className="mt-1 text-signal-green">pass rate {p.passRate}%</div>
      <div className="text-signal-blue">accuracy {p.accuracy}%</div>
      <div className="text-ink2">
        {p.scored} quer{p.scored === 1 ? "y" : "ies"} scored
      </div>
    </div>
  );
}

function StatPanel({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent: "green" | "blue";
}) {
  const glow = accent === "green" ? "shadow-glowGreen" : "shadow-glowBlue";
  const color = accent === "green" ? "text-signal-green" : "text-signal-blue";
  return (
    <div className={`rounded-lg border border-panelBorder bg-panel p-5 ${glow}`}>
      <div className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink2">
        {label}
      </div>
      <div className={`mt-2 font-mono text-3xl font-semibold ${color}`}>
        {value}
      </div>
    </div>
  );
}

function PulseStrip({ summaries }: { summaries: Summary[] }) {
  const data = summaries.map((s, i) => ({
    i,
    rate: toPercent(s.passRate),
  }));
  return (
    <div className="h-16 w-full opacity-90" style={{ filter: "drop-shadow(0 0 6px rgba(52,211,153,0.55))" }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="pulseFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#34D399" stopOpacity={0.35} />
              <stop offset="100%" stopColor="#34D399" stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="rate"
            stroke="#34D399"
            strokeWidth={1.5}
            fill="url(#pulseFill)"
            isAnimationActive={true}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function PassDot({ passed }: { passed: boolean | null }) {
  const color = passed ? "bg-signal-green" : "bg-signal-coral";
  return <span className={`inline-block h-2 w-2 rounded-full ${color}`} />;
}

export default function App() {
  const [summaries, setSummaries] = useState<Summary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchRunSummaries()
      .then(setSummaries)
      .catch((e) => setError(e.message ?? String(e)));
  }, []);

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-ink p-6 font-mono text-signal-coral">
        Couldn't reach Supabase: {error}. Check VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY in frontend/.env
      </div>
    );
  }

  if (!summaries) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-ink font-mono text-ink2">
        connecting…
      </div>
    );
  }

  if (summaries.length === 0) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-ink px-6 text-center font-mono text-ink2">
        <div className="text-signal-green">no eval runs logged yet</div>
        <div className="text-sm">
          run <code className="text-signal-blue">python backend/eval/run_eval.py</code> to log your first one
        </div>
      </div>
    );
  }

  // The stat panels describe the most recent run that scored anything; a run
  // where every query errored has no pass rate to show.
  const latest =
    [...summaries].reverse().find((s) => s.scored > 0) ??
    summaries[summaries.length - 1];
  const target = latest.run.target;
  // Only runs against the same target as the latest one, and only runs that
  // scored at least one query. Runs that errored before writing any results
  // (e.g. before API credits were added) would otherwise plot as 0%.
  const trend = summaries.filter(
    (s) => s.scored > 0 && s.run.target === target
  );
  const unscoredCount = summaries.filter(
    (s) => s.scored === 0 && s.run.target === target
  ).length;
  const otherTargets = [
    ...new Set(
      summaries
        .map((s) => s.run.target)
        .filter((t): t is string => !!t && t !== target)
    ),
  ];
  const trendData: TrendPoint[] = trend.map((s) => ({
    run: `#${s.runNumber}`,
    label: s.run.run_label || "unlabelled run",
    startedAt: s.run.started_at,
    scored: s.scored,
    passRate: toPercent(s.passRate),
    accuracy: toPercent(s.avgAccuracy),
  }));

  return (
    <div className="min-h-screen bg-ink pb-16 text-ink1">
      {/* Signature: oscilloscope pulse strip tracking pass-rate health */}
      <PulseStrip summaries={trend} />

      <div className="mx-auto max-w-5xl px-6">
        <header className="-mt-10 flex items-end justify-between border-b border-panelBorder pb-6">
          <div>
            <div className="font-mono text-[11px] uppercase tracking-[0.2em] text-ink2">
              eval-first agent · live instrumentation
            </div>
            <h1 className="mt-1 font-mono text-2xl font-semibold text-ink1">
              supabase-ai-eval
            </h1>
          </div>
          <div className="text-right font-mono text-xs text-ink2">
            <div>{summaries.length} run{summaries.length === 1 ? "" : "s"} logged</div>
            <div>latest: {new Date(latest.run.started_at).toLocaleString()}</div>
          </div>
        </header>

        <section className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <StatPanel label="pass rate (latest run)" value={pct(latest.passRate)} accent="green" />
          <StatPanel
            label="avg retrieval relevance"
            value={latest.avgRetrieval?.toFixed(2) ?? "—"}
            accent="blue"
          />
          <StatPanel
            label="avg latency"
            value={
              latest.avgLatency === null ? "—" : `${Math.round(latest.avgLatency)}ms`
            }
            accent="blue"
          />
        </section>

        <section className="mt-8 rounded-lg border border-panelBorder bg-panel p-5">
          <div className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink2">
            pass rate &amp; accuracy across runs{target ? ` · ${target}` : ""}
          </div>
          <div className="mt-4 h-56">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trendData}>
                <CartesianGrid stroke="#1F2A23" vertical={false} />
                <XAxis
                  dataKey="run"
                  tick={{ fill: "#7C9485", fontSize: 11 }}
                  interval="preserveStartEnd"
                  minTickGap={12}
                />
                <YAxis
                  tick={{ fill: "#7C9485", fontSize: 11 }}
                  domain={[0, 100]}
                  ticks={[0, 25, 50, 75, 100]}
                  tickFormatter={(v: number) => `${v}%`}
                  width={40}
                />
                <Tooltip content={<TrendTooltip />} />
                <Line type="linear" dataKey="passRate" stroke="#34D399" strokeWidth={2} dot={{ r: 3, fill: "#34D399" }} name="pass rate %" />
                <Line type="linear" dataKey="accuracy" stroke="#38BDF8" strokeWidth={2} dot={{ r: 3, fill: "#38BDF8" }} name="accuracy %" />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11px] text-ink2">
            <span><span className="text-signal-green">━</span> pass rate (of scored queries)</span>
            <span><span className="text-signal-blue">━</span> avg answer accuracy</span>
          </div>
          {(unscoredCount > 0 || otherTargets.length > 0) && (
            <div className="mt-2 font-mono text-[11px] text-ink2">
              {unscoredCount > 0 &&
                `${unscoredCount} run${unscoredCount === 1 ? "" : "s"} with no scored queries not plotted. `}
              {otherTargets.length > 0 &&
                `Runs for ${otherTargets.join(", ")} not shown.`}
            </div>
          )}
        </section>

        <section className="mt-8">
          <div className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink2">
            latest run · per-query results
          </div>
          <div className="mt-3 overflow-hidden rounded-lg border border-panelBorder">
            <table className="w-full border-collapse font-mono text-xs">
              <thead>
                <tr className="bg-panel text-left text-ink2">
                  <th className="px-3 py-2 font-medium"> </th>
                  <th className="px-3 py-2 font-medium">query</th>
                  <th className="px-3 py-2 font-medium">category</th>
                  <th className="px-3 py-2 font-medium">retrieval</th>
                  <th className="px-3 py-2 font-medium">accuracy</th>
                  <th className="px-3 py-2 font-medium">latency</th>
                </tr>
              </thead>
              <tbody>
                {latest.results.map((r: EvalResult) => (
                  <tr key={r.id} className="border-t border-panelBorder text-ink1">
                    <td className="px-3 py-2"><PassDot passed={r.passed} /></td>
                    <td className="max-w-xs truncate px-3 py-2">{r.eval_queries?.query}</td>
                    <td className="px-3 py-2 text-ink2">{r.eval_queries?.category}</td>
                    <td className="px-3 py-2 text-signal-blue">
                      {r.retrieval_relevance?.toFixed(2)}
                    </td>
                    <td className="px-3 py-2 text-signal-blue">
                      {r.answer_accuracy?.toFixed(2)}
                    </td>
                    <td className="px-3 py-2 text-ink2">{r.latency_ms}ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <footer className="mt-8 font-mono text-[11px] text-ink2">
          model: {latest.run.model_used} · embeddings: {latest.run.embed_model}
          {latest.run.git_commit ? ` · commit: ${latest.run.git_commit.slice(0, 7)}` : ""}
        </footer>
      </div>
    </div>
  );
}
