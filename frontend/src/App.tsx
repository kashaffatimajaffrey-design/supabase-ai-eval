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

function pct(n: number) {
  return `${Math.round(n * 100)}%`;
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
    rate: Math.round(s.passRate * 100),
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

  const latest = summaries[summaries.length - 1];
  const trendData = summaries.map((s, i) => ({
    run: s.run.run_label || `run ${i + 1}`,
    passRate: Math.round(s.passRate * 100),
    accuracy: Math.round(s.avgAccuracy * 100),
  }));

  return (
    <div className="min-h-screen bg-ink pb-16 text-ink1">
      {/* Signature: oscilloscope pulse strip tracking pass-rate health */}
      <PulseStrip summaries={summaries} />

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
            value={latest.avgRetrieval.toFixed(2)}
            accent="blue"
          />
          <StatPanel
            label="avg latency"
            value={`${Math.round(latest.avgLatency)}ms`}
            accent="blue"
          />
        </section>

        <section className="mt-8 rounded-lg border border-panelBorder bg-panel p-5">
          <div className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink2">
            pass rate &amp; accuracy across runs
          </div>
          <div className="mt-4 h-56">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trendData}>
                <CartesianGrid stroke="#1F2A23" vertical={false} />
                <XAxis dataKey="run" tick={{ fill: "#7C9485", fontSize: 11 }} />
                <YAxis tick={{ fill: "#7C9485", fontSize: 11 }} domain={[0, 100]} />
                <Tooltip
                  contentStyle={{
                    background: "#121815",
                    border: "1px solid #1F2A23",
                    fontFamily: "IBM Plex Mono, monospace",
                    fontSize: 12,
                  }}
                />
                <Line type="monotone" dataKey="passRate" stroke="#34D399" strokeWidth={2} dot={false} name="pass rate %" />
                <Line type="monotone" dataKey="accuracy" stroke="#38BDF8" strokeWidth={2} dot={false} name="accuracy %" />
              </LineChart>
            </ResponsiveContainer>
          </div>
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
