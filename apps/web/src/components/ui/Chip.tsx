/** Rule chip — colored by family (T=sky, E=violet, F=rose, modifier=slate). */
export function familyOf(ruleId: string): 'T' | 'E' | 'F' | 'M' {
  if (ruleId.startsWith('T')) return 'T';
  if (ruleId.startsWith('E')) return 'E';
  if (ruleId.startsWith('F')) return 'F';
  return 'M';
}

const FAMILY_CLASSES = {
  T: 'bg-accent-100 text-accent-600 border-accent/20',
  E: 'bg-violet-100 text-violet-700 border-violet-200',
  F: 'bg-rose-100 text-rose-700 border-rose-200',
  M: 'bg-slate-100 text-slate-500 border-slate-200',
} as const;

export const FAMILY_BAR = {
  T: 'bg-accent',
  E: 'bg-violet-500',
  F: 'bg-rose-500',
  M: 'bg-slate-400',
} as const;

export function RuleChip({ rule, title }: { rule: string; title?: string }) {
  return (
    <span
      title={title ?? rule}
      className={`inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[10px] font-semibold ${FAMILY_CLASSES[familyOf(rule)]}`}
    >
      {rule}
    </span>
  );
}
