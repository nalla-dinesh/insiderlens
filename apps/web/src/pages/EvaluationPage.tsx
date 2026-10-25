/** /evaluation — Phase 07 proof screen (spec §4):
 *  - run selector + Recompute button
 *  - metric cards: Precision / Recall / F1 / FPR (green when target met, red
 *    otherwise, tiny caption shows the goal), raw-counts strip beside them
 *  - 2×2 confusion matrix with counts AND %-labels (of their own squad)
 *  - scenario table: S1–S7 then L1–L5 (shaded), HIT/MISS, alert links,
 *    evidence one-liner verbatim from the alert's top reason (no paraphrase)
 *  - tuning panel: pick two runs → compare table with delta arrows. */
import { useCallback, useState } from 'react';
import toast from 'react-hot-toast';
import { Link, useSearchParams } from 'react-router-dom';

import { compareRuns, getEvaluation, listRuns, rerunAnalysis } from '../lib/api/evaluation';
import { dtFmt } from '../lib/format';
import { useApi } from '../lib/hooks';
import type { CompareReport, EvaluationReport, RunSummary } from '../lib/types';
import { CardSkeleton, EmptyState, ErrorState } from '../components/ui/States';

const pct = (x: number): string => `${(x * 100).toFixed(1)}%`;

export default function EvaluationPage({ reloadSignal }: { reloadSignal: number }) {
  const runsFetcher = useCallback((signal: AbortSignal) => listRuns(signal), []);
  const { data: runsData, loading, error, reload } = useApi(runsFetcher, [reloadSignal]);

  const [searchParams, setSearchParams] = useSearchParams();
  const selectedRaw = Number(searchParams.get('run'));
  const completed = (runsData?.items ?? []).filter((r) => r.status === 'COMPLETED');
  const selected = Number.isFinite(selectedRaw) && selectedRaw > 0
    ? selectedRaw
    : (completed[0]?.run_id ?? null);

  const [busy, setBusy] = useState(false);
  const recompute = async () => {
    setBusy(true);
    try {
      const { run_id } = await rerunAnalysis();
      toast.success(`Run #${run_id} completed — evaluating…`);
      reload();
      setSearchParams({ run: String(run_id) });
    } catch {
      /* interceptor toasts */
    } finally {
      setBusy(false);
    }
  };

  if (loading && !runsData) return <CardSkeleton rows={6} />;
  if (error && !runsData) return <ErrorState message={error} onRetry={reload} />;

  if (completed.length === 0) {
    return (
      <EmptyState
        title="No completed analysis runs yet."
        hint="Evaluation compares a run's alerts against ground truth (S1–S7 / L1–L5). Run the detection engine first."
        action={{ label: busy ? 'Running…' : '▶ Run analysis now', onClick: () => void recompute() }}
      />
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <h1 className="text-lg font-bold text-primary">Evaluation harness</h1>
          <p className="text-xs text-slate-500">
            Ground truth (S1–S7 suspicious · L1–L5 traps) vs each run's alerts. Ratios
            keep raw counts beside them — denominators are small, so truth first.
          </p>
        </div>
        <label className="ml-auto flex items-center gap-2 text-xs">
          <span className="text-[10px] font-semibold tracking-wider text-slate-400 uppercase">Run</span>
          <select
            value={selected ?? ''}
            onChange={(e) => setSearchParams({ run: e.target.value })}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm focus:border-accent focus:outline-none"
          >
            {completed.map((r: RunSummary) => (
              <option key={r.run_id} value={r.run_id}>
                #{r.run_id} · {dtFmt(r.started_at)} · {r.alert_count} alerts
              </option>
            ))}
          </select>
        </label>
        <button
          onClick={recompute}
          disabled={busy}
          className="rounded-lg bg-primary px-4 py-1.5 text-xs font-semibold text-white hover:bg-primary-700 disabled:opacity-50"
        >
          {busy ? 'Analyzing…' : '⟳ Recompute (new run)'}
        </button>
      </div>

      {selected !== null && <ReportBody runId={selected} allRuns={completed} />}
    </div>
  );
}

function ReportBody({ runId, allRuns }: { runId: number; allRuns: RunSummary[] }) {
  const fetcher = useCallback((signal: AbortSignal) => getEvaluation(runId, signal), [runId]);
  const { data, loading, error, reload } = useApi<EvaluationReport>(fetcher, [runId]);
  if (loading && !data) return <CardSkeleton rows={6} />;
  if (error && !data) return <ErrorState message={error} onRetry={reload} />;
  if (!data) return null;

  const c = data.counts;
  const cards = [
    { label: 'Precision', value: data.precision, goal: `≥ 0.85`, ok: data.targets.precision_passed },
    { label: 'Recall', value: data.recall, goal: `≥ 0.90`, ok: data.targets.recall_passed },
    { label: 'F1', value: data.f1, goal: 'harmonic mean', ok: data.targets.recall_passed && data.targets.precision_passed },
    { label: 'False-positive rate', value: data.fpr, goal: `≤ 0.05`, ok: data.targets.fpr_passed },
  ];

  const susp = data.scenario_rows.filter((r) => r.is_suspicious);
  const traps = data.scenario_rows.filter((r) => !r.is_suspicious);

  return (
    <>
      {/* metric cards */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        {cards.map((card) => (
          <div
            key={card.label}
            className={`rounded-xl border p-4 ${
              card.ok ? 'border-emerald-200 bg-emerald-50/60' : 'border-red-200 bg-red-50/60'
            }`}
          >
            <div className="text-[10px] font-semibold tracking-wider text-slate-500 uppercase">
              {card.label}
            </div>
            <div
              className={`font-mono text-3xl font-bold tabular-nums ${
                card.ok ? 'text-emerald-700' : 'text-red-700'
              }`}
            >
              {card.value.toFixed(4)}
            </div>
            <div className="mt-0.5 flex items-center justify-between text-[10px] text-slate-500">
              <span>{card.goal}</span>
              <span>{card.ok ? '● met' : '● missed'}</span>
            </div>
          </div>
        ))}
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="text-[10px] font-semibold tracking-wider text-slate-500 uppercase">Raw counts</div>
          <div className="mt-1 font-mono text-sm font-bold text-primary tabular-nums">
            TP {c.tp} · FP {c.fp}
            <br />
            FN {c.fn} · TN {c.tn}
          </div>
          <div className="mt-0.5 text-[10px] text-slate-400">
            {data.alerts_on_tagged_suspicious} on susp · {data.alerts_on_tagged_legit} on traps ·{' '}
            {data.alerts_unverified} unverified alerts
          </div>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-[280px_1fr]">
        {/* confusion matrix */}
        <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <h3 className="mb-2 text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
            Confusion matrix (scenario-level)
          </h3>
          <table className="w-full text-center">
            <thead>
              <tr className="text-[10px] text-slate-400">
                <th></th>
                <th className="py-1">pred: suspicious</th>
                <th className="py-1">pred: legit</th>
              </tr>
            </thead>
            <tbody>
              {(
                [
                  ['true: suspicious', 'tp', 'fn'],
                  ['true: legit (traps)', 'fp', 'tn'],
                ] as const
              ).map(([rowLabel, a, b]) => (
                <tr key={rowLabel}>
                  <td className="pr-2 text-left text-[10px] text-slate-500">{rowLabel}</td>
                  {[a, b].map((k) => {
                    const den = k === 'tp' || k === 'fn' ? c.tp + c.fn : c.fp + c.tn;
                    const v = c[k];
                    const bad = k === 'fp' ? v > 0 : false;
                    const good =
                      (k === 'tp' || k === 'tn') && v === den ? true : k === 'fn' || k === 'fp' ? false : true;
                    return (
                      <td
                        key={k}
                        className={`border border-slate-100 py-3 ${
                          bad ? 'bg-red-50' : good ? 'bg-emerald-50/50' : ''
                        }`}
                      >
                        <div className="font-mono text-xl font-bold tabular-nums text-primary">{v}</div>
                        <div className="font-mono text-[10px] uppercase text-slate-400">
                          {k} {den ? `· ${pct(v / den)}` : ''}
                        </div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        {/* scenario table */}
        <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
          <h3 className="border-b border-slate-100 px-4 py-2.5 text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
            Per-scenario results — S1–S7 must hit, L1–L5 must stay silent · run #{runId}
          </h3>
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-100 text-slate-400">
                <th className="px-4 py-2 font-medium">Scenario</th>
                <th className="py-2 font-medium">Verdict</th>
                <th className="py-2 font-medium">Matching alerts</th>
                <th className="py-2 pr-4 font-medium">Evidence (top reason, verbatim)</th>
              </tr>
            </thead>
            <tbody>
              {[...susp, ...traps].map((row, i) => (
                <tr
                  key={row.scenario_id + i}
                  className={`border-b border-slate-50 ${row.is_suspicious ? '' : 'bg-slate-50/60'}`}
                >
                  <td className="px-4 py-2 whitespace-nowrap">
                    <span className="font-mono font-semibold text-primary">{row.scenario_id}</span>
                    <span
                      className={`ml-2 rounded px-1.5 py-0.5 text-[9px] font-bold ${
                        row.is_suspicious ? 'bg-orange-100 text-orange-700' : 'bg-slate-200 text-slate-600'
                      }`}
                    >
                      {row.is_suspicious ? 'SUSPICIOUS' : 'TRAP'}
                    </span>
                  </td>
                  <td className="py-2">
                    <span
                      className={`font-mono font-bold ${
                        row.tag === 'TP'
                          ? 'text-emerald-600'
                          : row.tag === 'TN'
                            ? 'text-emerald-500'
                            : 'text-red-600'
                      }`}
                    >
                      {row.hit ? '◉' : '○'} {row.tag}
                    </span>
                  </td>
                  <td className="py-2 font-mono">
                    {row.matching_alert_ids.length === 0 ? (
                      <span className="text-slate-300">—</span>
                    ) : (
                      row.matching_alert_ids.slice(0, 4).map((id) => (
                        <Link key={id} className="mr-2 text-accent hover:underline" to={`/alerts/${id}`}>
                          #{id}
                        </Link>
                      ))
                    )}
                    {row.matching_alert_ids.length > 4 ? ` (+${row.matching_alert_ids.length - 4})` : ''}
                  </td>
                  <td className="max-w-105 py-2 pr-4 text-slate-600">
                    {row.note ? row.note : <span className="italic text-slate-300">silence — correct for traps</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>

      <ComparePanel allRuns={allRuns} current={runId} />
    </>
  );
}

// --------------------------------------------------------------- compare
function ComparePanel({ allRuns, current }: { allRuns: RunSummary[]; current: number }) {
  const [a, setA] = useState<number>(current);
  const [b, setB] = useState<number | ''>('');
  const [data, setData] = useState<CompareReport | null>(null);
  const [busy, setBusy] = useState(false);

  const runCompare = async () => {
    if (b === '' || a === b) return;
    setBusy(true);
    try {
      setData(await compareRuns(a, b));
    } catch {
      /* interceptor toasts */
    } finally {
      setBusy(false);
    }
  };

  const Delta = ({ v, invert }: { v: number; invert?: boolean }) => {
    const good = invert ? v <= 0 : v >= 0;
    if (v === 0) return <span className="text-slate-400">→ 0.0000</span>;
    return (
      <span className={good ? 'font-semibold text-emerald-600' : 'font-semibold text-red-600'}>
        {good ? '▲' : '▼'} {v > 0 ? '+' : ''}
        {v.toFixed(4)}
      </span>
    );
  };

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="mb-1 text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
        Tuning panel — compare two runs
      </h3>
      <p className="mb-3 text-xs text-slate-500">
        Used to journal knob experiments (see docs/TUNING.md): baseline vs tuned, deltas
        in one table — ↑ on recall/precision good, ↑ on FPR bad.
      </p>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
        <span className="text-slate-400">run A:</span>
        <select
          value={a}
          onChange={(e) => setA(Number(e.target.value))}
          className="rounded-lg border border-slate-200 bg-white px-2 py-1"
        >
          {allRuns.map((r) => (
            <option key={r.run_id} value={r.run_id}>#{r.run_id}</option>
          ))}
        </select>
        <span className="text-slate-400">run B:</span>
        <select
          value={b}
          onChange={(e) => setB(Number(e.target.value))}
          className="rounded-lg border border-slate-200 bg-white px-2 py-1"
        >
          <option value="">— pick —</option>
          {allRuns.filter((r) => r.run_id !== a).map((r) => (
            <option key={r.run_id} value={r.run_id}>#{r.run_id}</option>
          ))}
        </select>
        <button
          onClick={runCompare}
          disabled={busy || b === ''}
          className="rounded-lg bg-accent px-4 py-1.5 text-xs font-semibold text-white hover:bg-accent-600 disabled:opacity-50"
        >
          {busy ? 'Comparing…' : 'Compare'}
        </button>
      </div>
      {data && (
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-slate-100 text-slate-400">
              <th className="py-2 font-medium">Metric</th>
              <th className="py-2 font-medium">Run #{data.run_a.run_id}</th>
              <th className="py-2 font-medium">Run #{data.run_b.run_id}</th>
              <th className="py-2 font-medium">Δ (B − A)</th>
            </tr>
          </thead>
          <tbody className="font-mono tabular-nums">
            {(
              [
                ['precision', false],
                ['recall', false],
                ['f1', false],
                ['fpr', true],
              ] as const
            ).map(([m, invert]) => (
              <tr key={m} className="border-b border-slate-50">
                <td className="py-2 font-sans font-semibold text-slate-600 uppercase">{m}</td>
                <td className="py-2">{data.run_a[m].toFixed(4)}</td>
                <td className="py-2">{data.run_b[m].toFixed(4)}</td>
                <td className="py-2">
                  <Delta v={data.deltas[m]} invert={invert} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
