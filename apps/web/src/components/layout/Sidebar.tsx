/** Navy sidebar — dashboard / explorer live; cases + evaluation behind
 * phase gates (disabled with "soon" tooltip per spec §3.1). */
import { NavLink } from 'react-router-dom';

interface Item {
  to?: string;
  label: string;
  icon: string;
  disabled?: string;
}

const ITEMS: Item[] = [
  { to: '/', label: 'Dashboard', icon: '▦' },
  { to: '/explorer', label: 'Explorer', icon: '◎' },
  { to: '/cases', label: 'Cases', icon: '▤' },
  { to: '/evaluation', label: 'Evaluation', icon: '✓' },
];

export default function Sidebar() {
  return (
    <aside className="sticky top-0 z-30 flex h-screen w-56 shrink-0 flex-col bg-primary text-slate-200">
      <div className="border-b border-white/10 px-5 py-5">
        <div className="text-base font-bold tracking-tight text-white">
          Insider<span className="text-sky-400">Lens</span>
        </div>
        <div className="mt-0.5 text-[10px] tracking-widest text-slate-400 uppercase">
          graph fraud investigation
        </div>
      </div>
      <nav className="flex-1 space-y-1 px-3 py-4">
        {ITEMS.map((item) =>
          item.to ? (
            <NavLink
              key={item.label}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive ? 'bg-sky-400/15 text-sky-300' : 'text-slate-300 hover:bg-white/5 hover:text-white'
                }`
              }
            >
              <span className="w-4 text-center">{item.icon}</span>
              {item.label}
            </NavLink>
          ) : (
            <div
              key={item.label}
              title={item.disabled}
              className="flex cursor-not-allowed items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-slate-500"
            >
              <span className="w-4 text-center">{item.icon}</span>
              {item.label}
              <span className="ml-auto rounded-full border border-white/10 px-1.5 py-0.5 text-[9px] tracking-wide text-slate-500">
                soon
              </span>
            </div>
          ),
        )}
      </nav>
      <div className="border-t border-white/10 px-5 py-3 text-[10px] text-slate-500">
        Phase 05 · Frontend Core
      </div>
    </aside>
  );
}
