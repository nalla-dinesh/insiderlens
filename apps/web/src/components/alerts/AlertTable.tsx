/** Alert list table — row click → detail. Score column ALWAYS goes through
 * ScoreWithReason (the contract component); there is no other score renderer. */
import { useNavigate } from 'react-router-dom';

import { ageFmt, inrFmt } from '../../lib/format';
import type { AlertSummary, Band } from '../../lib/types';
import { BandBadge, StatusBadge } from '../ui/Badge';
import { RuleChip } from '../ui/Chip';
import ScoreWithReason from './ScoreWithReason';

const SCORE_TEXT: Record<Band, string> = {
  LOW: 'bg-slate-100 text-band-low',
  MEDIUM: 'bg-band-medium/10 text-band-medium',
  HIGH: 'bg-band-high/10 text-band-high',
  CRITICAL: 'bg-band-critical/10 text-band-critical',
};

export default function AlertTable({ items }: { items: AlertSummary[] }) {
  const navigate = useNavigate();
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50 text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
            <th className="px-4 py-3">Band</th>
            <th className="px-4 py-3">Score + reason</th>
            <th className="px-4 py-3">Rules</th>
            <th className="px-4 py-3">Entities</th>
            <th className="px-4 py-3 text-right">Max amount</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3 text-right">Age</th>
          </tr>
        </thead>
        <tbody>
          {items.map((a) => {
            const accs = a.entity_counts.accounts ?? 0;
            const emps = a.entity_counts.employees ?? 0;
            const others = a.entity_ids.length - accs - emps;
            return (
              <tr
                key={a.alert_id}
                onClick={() => navigate(`/alerts/${a.alert_id}`)}
                className="cursor-pointer border-b border-slate-100 transition-shadow last:border-0 hover:bg-slate-50 hover:shadow-[inset_2px_0_0_0_var(--color-accent)]"
              >
                <td className="px-4 py-3">
                  <BandBadge band={a.band} size="sm" />
                </td>
                <td className="px-4 py-3">
                  <ScoreWithReason
                    score={a.score}
                    reason={a.top_reasons[0] ?? 'no reason text'}
                    bandColor={SCORE_TEXT[a.band]}
                  />
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    {a.rule_set.map((r) => (
                      <RuleChip key={r} rule={r} />
                    ))}
                  </div>
                </td>
                <td className="px-4 py-3 font-mono text-xs whitespace-nowrap text-slate-500">
                  {accs > 0 && `${accs} acc`}
                  {accs > 0 && emps > 0 && ' · '}
                  {emps > 0 && `${emps} emp`}
                  {others > 0 && `${accs + emps ? ' · ' : ''}${others} cust`}
                </td>
                <td className="px-4 py-3 text-right font-mono text-xs tabular-nums text-primary">
                  {inrFmt(a.max_amount)}
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={a.status} />
                </td>
                <td className="px-4 py-3 text-right text-xs whitespace-nowrap text-slate-400">
                  {ageFmt(a.created_at)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
