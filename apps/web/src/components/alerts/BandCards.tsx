/** Per-band count header cards — sourced from AlertPage.band_counts (added
 * to the API in Phase 05 after reading the dashboard spec; noted in notes). */
import { BANDS, type Band } from '../../lib/types';

const CARD: Record<Band, string> = {
  LOW: 'border-band-low/30 text-band-low',
  MEDIUM: 'border-band-medium/30 text-band-medium',
  HIGH: 'border-band-high/30 text-band-high',
  CRITICAL: 'border-band-critical/30 text-band-critical',
};

const SELECTED: Record<Band, string> = {
  LOW: 'bg-band-low/10 ring-2 ring-band-low/50',
  MEDIUM: 'bg-band-medium/10 ring-2 ring-band-medium/50',
  HIGH: 'bg-band-high/10 ring-2 ring-band-high/50',
  CRITICAL: 'bg-band-critical/10 ring-2 ring-band-critical/50',
};

export default function BandCards({
  counts,
  selected,
  onSelect,
}: {
  counts: Record<Band, number> | undefined;
  selected: Band | null;
  onSelect: (band: Band | null) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {BANDS.map((band) => {
        const n = counts?.[band] ?? 0;
        const active = selected === band;
        return (
          <button
            key={band}
            onClick={() => onSelect(active ? null : band)}
            className={`rounded-xl border bg-white p-4 text-left shadow-sm transition-shadow hover:shadow-md ${CARD[band]} ${active ? SELECTED[band] : ''}`}
          >
            <div className="text-[11px] font-semibold tracking-wider uppercase">{band}</div>
            <div className="mt-1 font-mono text-2xl font-bold tabular-nums text-primary">{n}</div>
            <div className="mt-0.5 text-[10px] text-slate-400">
              {active ? 'click to clear filter' : 'click to filter'}
            </div>
          </button>
        );
      })}
    </div>
  );
}
