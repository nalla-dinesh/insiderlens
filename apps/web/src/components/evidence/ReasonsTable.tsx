/** Reasons table — full sentences, numbers bolded; WRAP, never ellipsis (P3). */
import { emphasise } from '../../lib/format';
import type { ReasonItem } from '../../lib/types';
import { RuleChip } from '../ui/Chip';

export default function ReasonsTable({ reasons }: { reasons: ReasonItem[] }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <h3 className="mb-3 text-xs font-semibold tracking-wider text-slate-400 uppercase">
        Why this score — every point explained
      </h3>
      <table className="w-full text-sm">
        <tbody>
          {reasons.map((r, i) => (
            <tr key={`${r.rule}-${i}`} className="border-b border-slate-100 align-top last:border-0">
              <td className="w-8 py-2 pr-2 font-mono text-xs text-slate-400">{i + 1}</td>
              <td className="w-20 py-2">
                <RuleChip rule={r.rule} title={r.text} />
              </td>
              <td className="w-16 py-2 text-right font-mono text-sm font-bold tabular-nums text-primary">
                +{r.pts}
              </td>
              <td className="py-2 pl-3 text-xs leading-relaxed text-slate-600">
                {emphasise(r.text).map((p, j) =>
                  p.bold ? (
                    <strong key={j} className="font-semibold text-primary">
                      {p.text}
                    </strong>
                  ) : (
                    <Numbered key={j} text={p.text} />
                  ),
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

/** Bold numeric tokens inside plain sentences (rules.yaml numbers, ids, hours). */
function Numbered({ text }: { text: string }) {
  const parts = text.split(/(\b\d[\d,.:%₹x-]*\b)/g);
  return (
    <>
      {parts.map((part, i) =>
        /\d/.test(part) && /^[\d,.:%₹x-]+$/.test(part) ? (
          <span key={i} className="font-mono font-semibold tabular-nums text-primary">
            {part}
          </span>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  );
}
