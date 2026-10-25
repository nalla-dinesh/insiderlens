/** Top bar: product name, last-run chip, Run Analysis (optimistic "Running…"). */
import { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';

import { listRuns, runAnalysis } from '../../lib/api/analysis';
import { dtFmt } from '../../lib/format';
import type { RunSummary } from '../../lib/types';

export default function TopBar({ onRunFinished }: { onRunFinished: () => void }) {
  const [running, setRunning] = useState(false);
  const [lastRun, setLastRun] = useState<RunSummary | null>(null);

  const refreshLastRun = useCallback(async () => {
    try {
      const list = await listRuns(1);
      setLastRun(list.items[0] ?? null);
    } catch {
      setLastRun(null); // API down — health card says so; no crash here
    }
  }, []);

  useEffect(() => {
    void refreshLastRun();
  }, [refreshLastRun]);

  const handleRun = useCallback(async () => {
    if (running) return;
    setRunning(true);
    const toastId = toast.loading('Running 14-rule analysis…');
    try {
      const rep = await runAnalysis();
      if (rep.status === 'COMPLETED') {
        const b = rep.alerts_by_band;
        toast.success(
          `Run #${rep.run_id} done in ${(rep.duration_ms / 1000).toFixed(1)}s — ` +
            `${rep.alerts_by_band.CRITICAL} critical, ${rep.alerts_by_band.HIGH} high, ` +
            `${b.MEDIUM} medium, ${b.LOW} low (${rep.signals_dropped} signals dropped)`,
        );
      } else {
        toast.error(`Run #${rep.run_id} ${rep.status}: ${rep.errors.join('; ')}`);
      }
    } catch {
      // interceptor already toasted the message
    } finally {
      toast.dismiss(toastId);
      setRunning(false);
      void refreshLastRun();
      onRunFinished();
    }
  }, [running, refreshLastRun, onRunFinished]);

  return (
    <header className="sticky top-0 z-20 flex items-center justify-between border-b border-slate-200 bg-white/90 px-6 py-3 backdrop-blur">
      <div className="flex items-center gap-4">
        <h1 className="text-lg font-bold tracking-tight text-primary">
          Insider<span className="text-accent">Lens</span>
        </h1>
        {lastRun && (
          <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 font-mono text-[11px] text-slate-500">
            last run #{lastRun.run_id} · {lastRun.status} · {dtFmt(lastRun.finished_at)}
          </span>
        )}
      </div>
      <button
        onClick={() => void handleRun()}
        disabled={running}
        className={`rounded-lg px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors ${
          running ? 'cursor-wait bg-slate-400' : 'bg-primary hover:bg-primary-700'
        }`}
      >
        {running ? 'Running…' : '▶ Run Analysis'}
      </button>
    </header>
  );
}
