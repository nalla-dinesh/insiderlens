/** Alert detail — 60/40 split: money-flow canvas LEFT, explainability proof
 * stack RIGHT. Spec §7.1: proof assembly, not visual candy. The score in the
 * header rides through ScoreWithReason — rendering a bare score won't compile. */
import { useCallback, useState } from 'react';
import type { Core } from 'cytoscape';
import { Link, useParams } from 'react-router-dom';

import ScoreWithReason from '../components/alerts/ScoreWithReason';
import ActionsFooter from '../components/evidence/ActionsFooter';
import ActivityTimeline from '../components/evidence/ActivityTimeline';
import InvariantBanner, { violatesInvariant } from '../components/evidence/InvariantBanner';
import ReasonsTable from '../components/evidence/ReasonsTable';
import ScoreCard from '../components/evidence/ScoreCard';
import ThresholdCompare from '../components/evidence/ThresholdCompare';
import CytoscapeCanvas from '../components/graph/CytoscapeCanvas';
import { StatusBadge } from '../components/ui/Badge';
import { RuleChip } from '../components/ui/Chip';
import { CardSkeleton, ErrorState } from '../components/ui/States';
import { getAlert } from '../lib/api/alerts';
import { dtFmt } from '../lib/format';
import { useApi } from '../lib/hooks';
import type { AlertDetail, Band } from '../lib/types';

const BAND_CHIP: Record<Band, string> = {
  LOW: 'bg-band-low/15 text-band-low',
  MEDIUM: 'bg-band-medium/15 text-band-medium',
  HIGH: 'bg-band-high/15 text-band-high',
  CRITICAL: 'bg-band-critical/15 text-band-critical',
};

export default function AlertDetailPage({ reloadSignal }: { reloadSignal: number }) {
  const { id } = useParams<{ id: string }>();
  const alertId = Number(id);
  const fetcher = useCallback((signal: AbortSignal) => getAlert(alertId, signal), [alertId]);
  const { data, loading, error, reload } = useApi<AlertDetail>(fetcher, [alertId, reloadSignal]);
  const [liveCy, setLiveCy] = useState<Core | null>(null);

  if (!id || Number.isNaN(alertId)) {
    return <ErrorState message={`invalid alert id "${id}"`} onRetry={() => reload()} />;
  }
  if (loading && !data) return <CardSkeleton rows={9} />;
  if (error && !data) return <ErrorState message={error} onRetry={reload} />;
  if (!data) return null;

  const broken = violatesInvariant(data.reasons, data.evidence);

  return (
    <div className="max-w-[96rem] space-y-4">
      {/* header strip */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border border-slate-200 bg-white px-5 py-3 shadow-sm">
        <Link to="/" className="text-xs font-medium text-accent hover:underline">
          ← queue
        </Link>
        <h1 className="font-mono text-sm font-semibold text-primary">Alert #{data.alert_id}</h1>
        <StatusBadge status={data.status} />
        <ScoreWithReason
          score={data.score}
          reason={data.reasons[0]?.text ?? 'no reasons recorded'}
          bandColor={BAND_CHIP[data.band]}
        />
        <span className="flex flex-wrap gap-1">
          {data.rule_set.map((r) => (
            <RuleChip key={r} rule={r} />
          ))}
        </span>
        <span className="ml-auto font-mono text-[10px] whitespace-nowrap text-slate-400 tabular-nums">
          {data.entity_type} · run #{data.run_id} · opened {dtFmt(data.created_at)}
        </span>
      </div>

      {broken && <InvariantBanner />}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[3fr_2fr]">
        {/* LEFT 60% — money flow */}
        <div>
          <CytoscapeCanvas graph={data.evidence.graph} band={data.band} height={560} onInit={setLiveCy} />
        </div>

        {/* RIGHT 40% — proof stack */}
        <div className="space-y-4">
          <ScoreCard score={data.score} band={data.band} reasons={data.reasons} />
          <ReasonsTable reasons={data.reasons} />
          <ThresholdCompare thresholds={data.evidence.thresholds} />
        </div>
      </div>

      <ActivityTimeline events={data.evidence.timeline} />
      <ActionsFooter
        alertId={data.alert_id}
        status={data.status}
        onChanged={(next) => {
          void next;
          reload();
        }}
        caseId={data.case_id ?? null}
        cy={liveCy}
        band={data.band}
        topReason={data.reasons[0]?.text ?? 'unspecified pattern'}
        entityCount={data.entity_ids.length}
      />
    </div>
  );
}
