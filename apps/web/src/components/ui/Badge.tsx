/** Band badge = colored bg-10% + colored text + left dot (design system §2). */
import type { Band } from '../../lib/types';

const STYLES: Record<Band, string> = {
  LOW: 'bg-band-low/10 text-band-low',
  MEDIUM: 'bg-band-medium/10 text-band-medium',
  HIGH: 'bg-band-high/10 text-band-high',
  CRITICAL: 'bg-band-critical/10 text-band-critical',
};

const DOT: Record<Band, string> = {
  LOW: 'bg-band-low',
  MEDIUM: 'bg-band-medium',
  HIGH: 'bg-band-high',
  CRITICAL: 'bg-band-critical',
};

export function BandBadge({ band, size = 'md' }: { band: Band; size?: 'sm' | 'md' }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-semibold ${STYLES[band]} ${
        size === 'sm' ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-xs'
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${DOT[band]}`} />
      {band}
    </span>
  );
}

const STATUS_STYLES: Record<string, string> = {
  OPEN: 'bg-accent-100 text-accent-600',
  ACKNOWLEDGED: 'bg-slate-100 text-slate-600',
  IN_REVIEW: 'bg-band-medium/10 text-band-medium',
  RESOLVED: 'bg-success-100 text-success',
  DISMISSED: 'bg-slate-100 text-slate-400',
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${
        STATUS_STYLES[status] ?? 'bg-slate-100 text-slate-500'
      }`}
    >
      {status}
    </span>
  );
}
