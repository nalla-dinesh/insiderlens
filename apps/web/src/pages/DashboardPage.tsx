/** Dashboard — band filter pills (server-counted) + filters + alert queue.
 * Signals ≠ alerts: ONLY persisted, deduped alerts render. Every score cell
 * shows its top reason next to the number (component-level contract). */
import { useCallback, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import AlertTable from '../components/alerts/AlertTable';
import BandCards from '../components/alerts/BandCards';
import FilterBar, { type Filters } from '../components/alerts/FilterBar';
import { CardSkeleton, EmptyState, ErrorState } from '../components/ui/States';
import { listAlerts } from '../lib/api/alerts';
import { useApi } from '../lib/hooks';
import type { AlertPage, Band, AlertStatus } from '../lib/types';

const PAGE_SIZE = 20;

export default function DashboardPage({ reloadSignal }: { reloadSignal: number }) {
  const navigate = useNavigate();
  const [filters, setFilters] = useState<Filters>({});
  const [page, setPage] = useState(1); // 1-based UI; API gets offset

  const params = useMemo(
    () => ({
      band: (filters.band as Band | undefined) ?? undefined,
      rule: filters.rule,
      status: (filters.status as AlertStatus | undefined) ?? undefined,
      entity: filters.entity,
      limit: PAGE_SIZE,
      offset: (page - 1) * PAGE_SIZE,
    }),
    [filters, page],
  );

  const fetcher = useCallback((signal: AbortSignal) => listAlerts({ ...params, signal }), [params]);
  const { data, loading, error, reload } = useApi<AlertPage>(fetcher, [params, reloadSignal]);

  const pageCount = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  const patchFilters = (f: Filters) => {
    setFilters(f);
    setPage(1);
  };

  if (loading && !data) return <CardSkeleton rows={9} />;
  if (error && !data) return <ErrorState message={error} onRetry={reload} />;

  return (
    <div className="max-w-7xl space-y-4">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-lg font-bold text-primary">Alert queue</h1>
          <p className="text-xs text-slate-500">
            {data
              ? `${data.total} persisted alerts — deduped per case, each scoring = Σ(on-screen reasons)`
              : 'loading…'}
          </p>
        </div>
        {loading && <span className="text-xs text-slate-400">refreshing…</span>}
      </div>

      {/* band pills reflect the FILTERED set (band itself excluded server-side),
          so threshold filters never lie about the rest of the queue */}
      <BandCards
        counts={data?.band_counts}
        selected={(filters.band as Band | undefined) ?? null}
        onSelect={(b) => patchFilters({ ...filters, band: b ?? undefined })}
      />

      <FilterBar value={filters} onChange={patchFilters} />

      {data && data.items.length === 0 ? (
        <EmptyState
          title="Funnel empty — everything was sane."
          hint="The engine ran and nothing crossed the persistence bar, or your filters exclude everything. Loosen the filters, or run analysis again after a fresh batch lands."
          action={{ label: 'Take me to the Explorer anyway →', onClick: () => navigate('/explorer') }}
        />
      ) : data ? (
        <>
          <AlertTable items={data.items} />
          <div className="flex items-center justify-between">
            <p className="font-mono text-xs text-slate-400 tabular-nums">
              page {page} / {pageCount} · {data.items.length} rows
            </p>
            <div className="flex gap-2">
              <PageBtn label="← Prev" disabled={page <= 1} onClick={() => setPage(page - 1)} />
              <PageBtn
                label="Next →"
                disabled={page >= pageCount}
                onClick={() => setPage(page + 1)}
              />
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}

function PageBtn({
  label,
  disabled,
  onClick,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      disabled={disabled}
      onClick={onClick}
      className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-40"
    >
      {label}
    </button>
  );
}
