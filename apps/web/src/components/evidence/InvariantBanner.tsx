/** DATA INVARIANT VIOLATION banner — evidence/reasons empty should be
 * IMPOSSIBLE (DB CHECK + tests). If it ever happens, shout instead of hiding. */
import type { EvidencePayload, ReasonItem } from '../../lib/types';

export function violatesInvariant(
  reasons: ReasonItem[] | undefined,
  evidence: EvidencePayload | undefined,
): boolean {
  if (!reasons || reasons.length === 0) return true;
  if (!evidence) return true;
  const recs = evidence.records;
  if (!recs || (recs.txn_ids.length === 0 && recs.log_ids.length === 0)) return true;
  return false;
}

export default function InvariantBanner() {
  return (
    <div className="rounded-xl border-2 border-danger bg-danger-100 p-5">
      <p className="text-sm font-bold tracking-wide text-danger uppercase">
        ⚠ Data invariant violation
      </p>
      <p className="mt-1 text-xs text-danger/80">
        This alert reached the analyst queue without reasons or evidence. The DB CHECK constraints
        and the pipeline law BOTH forbid this — treat the persistence layer as compromised and file
        an incident. Do NOT act on this alert.
      </p>
    </div>
  );
}
