/** Score card — big score + band badge + CONTRIBUTION STACKED BAR (the
 * arithmetic IS the design: every +pts glows in the bar, colored per family). */
import type { Band, ReasonItem } from '../../lib/types';
import { BandBadge } from '../ui/Badge';
import { FAMILY_BAR, familyOf, RuleChip } from '../ui/Chip';

export default function ScoreCard({
  score,
  band,
  reasons,
}: {
  score: number;
  band: Band;
  reasons: ReasonItem[];
}) {
  const total = reasons.reduce((sum, r) => sum + r.pts, 0);
  const scale = Math.max(total, 1);
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
          Explainable score
        </span>
        <BandBadge band={band} />
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="font-mono text-4xl font-bold tabular-nums text-primary">{score}</span>
        <span className="text-xs text-slate-400">= sum of {reasons.length} reasons below</span>
      </div>

      <div className="mt-4 flex h-3 w-full overflow-hidden rounded-full bg-slate-100">
        {reasons.map((r, i) => (
          <div
            key={`${r.rule}-${i}`}
            style={{ width: `${(r.pts / scale) * 100}%` }}
            className={`${FAMILY_BAR[familyOf(r.rule)]} transition-all`} aria-label={`${r.rule} +${r.pts} pts`}
            title={`${r.rule} +${r.pts}`}
          />
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5 text-[10px] text-slate-500">
        {reasons.map((r, i) => (
          <span key={`${r.rule}-legend-${i}`} className="inline-flex items-center gap-1">
            <span className={`h-2 w-2 rounded-sm ${FAMILY_BAR[familyOf(r.rule)]}`} />
            <RuleChip rule={r.rule} />
            <span className="font-mono font-semibold">+{r.pts}</span>
          </span>
        ))}
      </div>
      {total !== score && (
        <p className="mt-3 rounded-lg border border-danger/40 bg-danger-100 px-3 py-2 text-xs font-semibold text-danger">
          ARITHMETIC MISMATCH — reasons sum to {total} but score is {score}. This should be
          impossible (iron law test guards it); report immediately.
        </p>
      )}
    </section>
  );
}
