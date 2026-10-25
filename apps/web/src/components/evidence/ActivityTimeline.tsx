/** Activity timeline — vertical line; TXN sky / EMPLOYEE violet; auto-scrolls
 * to the first EMPLOYEE event (the insider story starts there). */
import { useEffect, useRef } from 'react';

import { dtFmt } from '../../lib/format';
import type { TimelineEvent } from '../../lib/types';

const DOT = {
  TXN: 'bg-accent border-accent/30',
  EMPLOYEE: 'bg-violet-500 border-violet-200',
} as const;

const KIND_LABEL = {
  TXN: 'txn',
  EMPLOYEE: 'emp',
} as const;

export default function ActivityTimeline({ events }: { events: TimelineEvent[] }) {
  const firstEmpRef = useRef<HTMLLIElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (firstEmpRef.current && containerRef.current) {
      containerRef.current.scrollTo({
        top: firstEmpRef.current.offsetTop - 40,
        behavior: 'smooth',
      });
    }
  }, [events]);

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <h3 className="mb-3 text-xs font-semibold tracking-wider text-slate-400 uppercase">
        Activity timeline ({events.length} events)
      </h3>
      <div ref={containerRef} className="max-h-96 overflow-y-auto pr-2">
        <ol className="relative border-l border-slate-200">
          {events.map((e, i) => (
            <li
              key={`${e.ts}-${e.ref_id}-${i}`}
              ref={e.kind === 'EMPLOYEE' && !firstEmpRef.current ? (el) => { if (firstEmpRef.current === null) firstEmpRef.current = el; } : undefined}
              className="group ml-4 py-2"
            >
              <span
                className={`absolute -left-[7px] mt-1.5 h-3.5 w-3.5 rounded-full border-2 bg-white ${DOT[e.kind]}`}
                title={`ref ${e.kind}#${e.ref_id}`}
              />
              <div className="flex items-start justify-between gap-3">
                <p className="text-xs leading-relaxed text-slate-700">{e.label}</p>
                <span className="font-mono text-[10px] whitespace-nowrap text-slate-400 tabular-nums">
                  {dtFmt(e.ts)}
                </span>
              </div>
              <span className="text-[9px] font-semibold tracking-wide text-slate-400 uppercase opacity-0 transition-opacity group-hover:opacity-100">
                {KIND_LABEL[e.kind]} #{e.ref_id}
              </span>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
