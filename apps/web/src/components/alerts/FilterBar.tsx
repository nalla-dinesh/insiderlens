/** Server-driven filter bar: band chips, rule select, status select, entity id. */
import { useState } from 'react';

import { RULE_IDS, STATUSES } from '../../lib/types';

export interface Filters {
  band?: string;
  rule?: string;
  status?: string;
  entity?: number;
}

export default function FilterBar({
  value,
  onChange,
}: {
  value: Filters;
  onChange: (f: Filters) => void;
}) {
  const [entityText, setEntityText] = useState(value.entity?.toString() ?? '');

  const set = (patch: Partial<Filters>) => onChange({ ...value, ...patch });

  return (
    <div className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <label className="flex flex-col gap-1">
        <span className="text-[10px] font-semibold tracking-wider text-slate-400 uppercase">Rule</span>
        <select
          value={value.rule ?? ''}
          onChange={(e) => set({ rule: e.target.value || undefined })}
          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-primary focus:border-accent focus:outline-none"
        >
          <option value="">All rules</option>
          {RULE_IDS.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-[10px] font-semibold tracking-wider text-slate-400 uppercase">Status</span>
        <select
          value={value.status ?? ''}
          onChange={(e) => set({ status: e.target.value || undefined })}
          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-primary focus:border-accent focus:outline-none"
        >
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
          Entity id (account / employee)
        </span>
        <input
          value={entityText}
          onChange={(e) => {
            const t = e.target.value.trim();
            setEntityText(t);
            set({ entity: /^\d+$/.test(t) ? Number(t) : undefined });
          }}
          inputMode="numeric"
          placeholder="e.g. 200071"
          className="w-44 rounded-lg border border-slate-200 bg-white px-3 py-1.5 font-mono text-sm text-primary focus:border-accent focus:outline-none"
        />
      </label>

      <button
        onClick={() => {
          setEntityText('');
          onChange({ band: value.band });
        }}
        className="ml-auto rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-500 transition-colors hover:border-accent hover:text-accent"
      >
        Clear filters
      </button>
    </div>
  );
}
