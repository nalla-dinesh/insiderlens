/** Display formatting — NEVER on the server (pitfall P2): server sends numbers,
 * the client formats with en-IN grouping and date-fns. */
import { format, formatDistanceToNowStrict, parseISO } from 'date-fns';

const inr = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
});

export function inrFmt(amount: number | null | undefined): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return '—';
  return inr.format(amount);
}

export function dtFmt(iso: string | null | undefined): string {
  if (!iso) return '—';
  return format(parseISO(iso), 'dd MMM yyyy, HH:mm');
}

export function ageFmt(iso: string | null | undefined): string {
  if (!iso) return '—';
  return `${formatDistanceToNowStrict(parseISO(iso))} ago`;
}

export function timeShort(iso: string): string {
  return format(parseISO(iso), 'dd MMM, HH:mm');
}

export function pct(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`;
}

/** Optional **bold** inline markers in reason sentences (we own the format). */
export function emphasise(text: string): Array<{ bold: boolean; text: string }> {
  return text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map((part) =>
    part.startsWith('**') && part.endsWith('**')
      ? { bold: true, text: part.slice(2, -2) }
      : { bold: false, text: part },
  );
}
