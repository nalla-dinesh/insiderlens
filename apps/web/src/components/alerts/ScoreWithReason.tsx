/** COMPONENT-LEVEL CONTRACT (DoD): a score is NEVER rendered without its
 * reason. There is intentionally no plain <Score/> component anywhere —
 * the only way to show a number is through this component, which requires
 * a reason text and renders it beside the number. */
interface Props {
  score: number;
  reason: string; // REQUIRED — a bare score cannot compile here
  bandColor: string;
}

export default function ScoreWithReason({ score, reason, bandColor }: Props) {
  return (
    <div className="flex items-center gap-2">
      <span
        className={`inline-flex min-w-10 justify-center rounded-md px-2 py-0.5 font-mono text-sm font-bold tabular-nums ${bandColor}`}
      >
        {score}
      </span>
      <span className="max-w-64 truncate text-[11px] text-slate-500" title={reason}>
        {reason.replace(/^\[[A-Z0-9]+\]\s*/, '')}
      </span>
    </div>
  );
}
