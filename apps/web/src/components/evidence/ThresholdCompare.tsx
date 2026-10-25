/** Threshold compare — every gate the engine used: observed vs limit, with
 * over/under coloring and the rules.yaml source pointer. */
import type { ThresholdGate } from '../../lib/types';

function numeric(v: string | number): number | null {
  const n = typeof v === 'number' ? v : Number.parseFloat(v);
  return Number.isFinite(n) ? n : null;
}

export default function ThresholdCompare({
  thresholds,
}: {
  thresholds: Record<string, ThresholdGate>;
}) {
  const entries = Object.entries(thresholds);
  if (entries.length === 0) return null;
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <h3 className="mb-3 text-xs font-semibold tracking-wider text-slate-400 uppercase">
        Threshold gates (source: rules.yaml / roles table)
      </h3>
      <div className="space-y-3">
        {entries.map(([key, gate]) => {
          const obs = numeric(gate.observed);
          const lim = numeric(gate.limit);
          const comparable = obs !== null && lim !== null && lim !== 0;
          const ratio = comparable ? obs / (lim as number) : null; // same-lane comparison
          return (
            <div key={key}>
              <div className="flex items-baseline justify-between gap-2">
                <span className="font-mono text-[11px] break-all text-slate-600">{key}</span>
                <span className="font-mono text-[10px] whitespace-nowrap text-slate-400">
                  {gate.source}
                </span>
              </div>
              <div className="mt-1 flex items-center gap-2">
                <div className="flex h-1.5 flex-1 overflow-visible rounded-full bg-slate-100">
                  {ratio !== null ? (
                    <div
                      className={`h-full rounded-full ${ratio >= 1 ? 'bg-band-critical' : 'bg-success'}`}
                      style={{ width: `${Math.min(ratio * 100, 100)}%` }}
                    />
                  ) : (
                    <div className="h-full w-1/2 rounded-full bg-slate-300" />
                  )}
                </div>
                <span
                  className={`font-mono text-xs font-semibold tabular-nums whitespace-nowrap ${
                    ratio !== null && ratio >= 1 ? 'text-band-critical' : 'text-slate-600'
                  }`}
                >
                  {String(gate.observed)} <span className="text-slate-400">vs</span> {String(gate.limit)}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
