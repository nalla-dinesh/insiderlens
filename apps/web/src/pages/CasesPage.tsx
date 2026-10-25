/** Cases board — 5 status columns; click card → right drawer with full case
 * (linked alerts, notes thread, assignee dropdown, only-legal status buttons,
 * export ZIP). Optimistic status updates with rollback (spec §2.3). */
import { useCallback, useState } from 'react';
import toast from 'react-hot-toast';
import { Link, useSearchParams } from 'react-router-dom';

import {
  addCaseNote,
  downloadBlob,
  exportCaseZip,
  getCase,
  listAnalysts,
  listCasesBoard,
  patchCase,
} from '../lib/api/cases';
import { dtFmt } from '../lib/format';
import { useApi } from '../lib/hooks';
import {
  CASE_TRANSITIONS,
  type AnalystOut,
  type Band,
  type CaseBoardItem,
  type CaseDetail,
  type CaseStatus,
} from '../lib/types';
import { BandBadge } from '../components/ui/Badge';
import { CardSkeleton, EmptyState, ErrorState } from '../components/ui/States';

const STATUS_STYLE: Record<CaseStatus, { chip: string; dot: string; label: string }> = {
  OPEN: { chip: 'bg-sky-100 text-sky-700', dot: 'bg-sky-500', label: 'Open' },
  IN_PROGRESS: { chip: 'bg-amber-100 text-amber-700', dot: 'bg-amber-500', label: 'In progress' },
  ESCALATED: { chip: 'bg-orange-100 text-orange-700', dot: 'bg-orange-600', label: 'Escalated' },
  CLOSED_TRUE: { chip: 'bg-emerald-100 text-emerald-700', dot: 'bg-emerald-600', label: 'Closed · fraud' },
  CLOSED_FALSE: { chip: 'bg-slate-200 text-slate-600', dot: 'bg-slate-400', label: 'Closed · benign' },
};

const BAND_BAR: Record<Band, string> = {
  LOW: 'border-l-band-low',
  MEDIUM: 'border-l-band-medium',
  HIGH: 'border-l-band-high',
  CRITICAL: 'border-l-band-critical',
};

function initials(name: string): string {
  return name
    .split(/\s+/)
    .map((p) => p[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();
}

function ageOf(iso: string): string {
  const days = Math.max(0, (Date.now() - new Date(iso).getTime()) / 86_400_000);
  return days < 1 ? 'today' : days < 2 ? '1d old' : `${Math.floor(days)}d old`;
}

export default function CasesPage({ reloadSignal }: { reloadSignal: number }) {
  const fetcher = useCallback((signal: AbortSignal) => listCasesBoard(signal), []);
  const { data: board, loading, error, reload } = useApi(fetcher, [reloadSignal]);

  const analystsFetcher = useCallback((signal: AbortSignal) => listAnalysts(signal), []);
  const { data: analysts } = useApi<AnalystOut[]>(analystsFetcher, []);

  const [searchParams, setSearchParams] = useSearchParams();
  const focusParam = Number(searchParams.get('focus'));
  const [focusId, setFocusId] = useState<number | null>(
    Number.isFinite(focusParam) && focusParam > 0 ? focusParam : null,
  );

  const openCase = (id: number) => {
    setFocusId(id);
    setSearchParams({ focus: String(id) });
  };
  const closeDrawer = () => {
    setFocusId(null);
    setSearchParams({});
  };

  if (loading && !board) return <CardSkeleton rows={8} />;
  if (error && !board) return <ErrorState message={error} onRetry={reload} />;
  if (!board) return null;

  const cardCount = Object.values(board.groups).reduce((s, g) => s + g.length, 0);

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-lg font-bold text-primary">Case board</h1>
          <p className="text-xs text-slate-500">
            {cardCount} case{cardCount === 1 ? '' : 's'} · alerts converted into tracked
            investigations. Status moves are audited into the notes thread.
          </p>
        </div>
      </div>

      {cardCount === 0 ? (
        <EmptyState
          title="No cases yet — the queue feeds here."
          hint="Open a HIGH/CRITICAL alert and hit 'Convert to case'. The alert's full evidence rides along."
          action={{ label: 'Go to alert queue →', onClick: () => (location.href = '/') }}
        />
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3 xl:grid-cols-5">
          {board.statuses.map((status) => (
            <div key={status} className="min-h-40 rounded-xl border border-slate-200 bg-slate-50/70 p-2.5">
              <div className="mb-2 flex items-center gap-2 px-1">
                <span className={`h-2 w-2 rounded-full ${STATUS_STYLE[status].dot}`} />
                <span className="text-[10px] font-semibold tracking-wider text-slate-500 uppercase">
                  {STATUS_STYLE[status].label}
                </span>
                <span className="ml-auto font-mono text-[10px] text-slate-400">
                  {board.groups[status].length}
                </span>
              </div>
              <div className="space-y-2">
                {board.groups[status].map((c) => (
                  <CaseCard key={c.case_id} item={c} onClick={() => openCase(c.case_id)} />
                ))}
                {board.groups[status].length === 0 && (
                  <p className="px-1 py-3 text-center text-[10px] text-slate-400">empty</p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {focusId !== null && (
        <CaseDrawer
          caseId={focusId}
          analysts={analysts ?? []}
          onClose={closeDrawer}
          onChanged={reload}
        />
      )}
    </div>
  );
}

function CaseCard({ item, onClick }: { item: CaseBoardItem; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`block w-full rounded-lg border border-slate-200 border-l-4 bg-white p-3 text-left shadow-sm transition-shadow hover:shadow-md ${item.band ? BAND_BAR[item.band] : 'border-l-slate-300'}`}
    >
      <div className="mb-1 flex items-center justify-between gap-2">
        {item.band && <BandBadge band={item.band} />}
        <span className="font-mono text-[10px] text-slate-400">case #{item.case_id}</span>
      </div>
      <p className="line-clamp-2 text-xs font-medium leading-snug text-slate-700">{item.title}</p>
      <div className="mt-2 flex items-center justify-between text-[10px] text-slate-400">
        <span className="inline-flex items-center gap-1.5">
          {item.assignee ? (
            <>
              <span className="flex h-4.5 w-4.5 items-center justify-center rounded-full bg-primary text-[8px] font-bold text-white">
                {initials(item.assignee)}
              </span>
              {item.assignee.split(' ')[0]}
            </>
          ) : (
            'unassigned'
          )}
        </span>
        <span>
          {item.alert_count} alert{item.alert_count === 1 ? '' : 's'} · {ageOf(item.created_at)}
        </span>
      </div>
    </button>
  );
}

// ------------------------------------------------------------------ drawer
function CaseDrawer({
  caseId,
  analysts,
  onClose,
  onChanged,
}: {
  caseId: number;
  analysts: AnalystOut[];
  onClose: () => void;
  onChanged: () => void;
}) {
  const fetcher = useCallback((signal: AbortSignal) => getCase(caseId, signal), [caseId]);
  const { data, loading, error, reload } = useApi<CaseDetail>(fetcher, [caseId]);
  const [optimistic, setOptimistic] = useState<CaseDetail | null>(null);
  const detail = optimistic ?? data;
  const [noteText, setNoteText] = useState('');
  const [busy, setBusy] = useState(false);

  const closed = detail ? detail.status.startsWith('CLOSED') : false;

  const apply = async (patch: Parameters<typeof patchCase>[1], revertTo: CaseDetail) => {
    setBusy(true);
    try {
      const updated = await patchCase(caseId, patch);
      setOptimistic(null);
      void updated;
      reload();
      onChanged();
    } catch {
      setOptimistic(revertTo); // rollback on error (spec §2.3)
    } finally {
      setBusy(false);
    }
  };

  const setStatus = (next: CaseStatus) => {
    if (!detail) return;
    const before = detail;
    setOptimistic({ ...detail, status: next });
    void apply({ status: next, actor: detail.assignee ?? 'analyst' }, before);
  };

  const setAssignee = (name: string) => {
    if (!detail) return;
    const before = detail;
    setOptimistic({ ...detail, assignee: name || null });
    void apply({ assignee: name, actor: detail.assignee ?? 'analyst' }, before);
  };

  const submitNote = async () => {
    if (!noteText.trim() || !detail || busy) return;
    setBusy(true);
    try {
      await addCaseNote(caseId, { body: noteText.trim(), author: detail.assignee ?? 'analyst' });
      setNoteText('');
      reload();
    } catch {
      /* interceptor toasts */
    } finally {
      setBusy(false);
    }
  };

  const doExport = async () => {
    setBusy(true);
    try {
      const blob = await exportCaseZip(caseId);
      downloadBlob(blob, `case_${caseId}_evidence.zip`);
      toast.success('Evidence ZIP downloaded — openable offline.');
    } catch {
      /* interceptor toasts */
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-primary/40 backdrop-blur-[1px]"
        onClick={onClose}
        aria-hidden
      />
      <aside data-testid="case-drawer" className="fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col bg-white shadow-2xl">
        {loading && !detail ? (
          <div className="p-5">
            <CardSkeleton rows={6} />
          </div>
        ) : error && !detail ? (
          <div className="p-5">
            <ErrorState message={error} onRetry={reload} />
          </div>
        ) : detail ? (
          <>
            {/* header */}
            <div className="flex items-center gap-3 border-b border-slate-200 px-5 py-4">
              <h2 className="font-mono text-sm font-bold text-primary">Case #{detail.case_id}</h2>
              {detail.band && <BandBadge band={detail.band} />}
              <span
                className={`rounded-full px-2 py-0.5 text-[10px] font-semibold tracking-wide uppercase ${STATUS_STYLE[detail.status].chip}`}
              >
                {STATUS_STYLE[detail.status].label}
              </span>
              <button
                onClick={onClose}
                className="ml-auto rounded-lg px-2 py-1 text-slate-400 hover:bg-slate-100"
                aria-label="Close case drawer"
              >
                ✕
              </button>
            </div>

            <div className="flex-1 space-y-5 overflow-y-auto px-5 py-4">
              {/* title (editable while open) */}
              <div>
                <TitleEditor
                  value={detail.title}
                  disabled={closed || busy}
                  onSave={(title) => {
                    const before = detail;
                    setOptimistic({ ...detail, title });
                    void apply({ title, actor: detail.assignee ?? 'analyst' }, before);
                  }}
                />
                <p className="mt-1 font-mono text-[10px] text-slate-400 tabular-nums">
                  opened {dtFmt(detail.created_at)}
                  {detail.closed_at ? ` · closed ${dtFmt(detail.closed_at)}` : ''}
                  {closed ? ' · immutable (P5)' : ''}
                </p>
              </div>

              {/* status machine — only legal transitions enabled */}
              <section>
                <h3 className="mb-2 text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
                  Status (legal moves only)
                </h3>
                <div className="flex flex-wrap gap-2">
                  {(Object.keys(STATUS_STYLE) as CaseStatus[]).map((st) => {
                    const legal = detail.status === st || CASE_TRANSITIONS[detail.status].includes(st);
                    return (
                      <button
                        key={st}
                        disabled={!legal || busy}
                        onClick={() => setStatus(st)}
                        title={
                          legal
                            ? detail.status === st
                              ? 'current status'
                              : `Move ${detail.status} → ${st}`
                            : `Illegal: ${detail.status} → ${st} is not an allowed transition`
                        }
                        className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors ${
                          detail.status === st
                            ? 'border-accent bg-accent text-white'
                            : legal
                              ? 'border-slate-200 text-slate-600 hover:border-accent hover:text-accent'
                              : 'cursor-not-allowed border-slate-100 text-slate-300'
                        }`}
                      >
                        {STATUS_STYLE[st].label}
                      </button>
                    );
                  })}
                </div>
              </section>

              {/* assignee */}
              <section>
                <h3 className="mb-2 text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
                  Assignee (analyst directory)
                </h3>
                <select
                  value={detail.assignee ?? ''}
                  disabled={closed || busy}
                  onChange={(e) => setAssignee(e.target.value)}
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-primary focus:border-accent focus:outline-none disabled:opacity-50"
                >
                  <option value="">— unassigned</option>
                  {analysts.map((a) => (
                    <option key={a.emp_id} value={a.name}>
                      {a.name} · {a.role} ({a.branch})
                    </option>
                  ))}
                </select>
              </section>

              {/* linked alerts */}
              <section>
                <h3 className="mb-2 text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
                  Linked alerts ({detail.alert_ids.length}) — full evidence rides inside
                </h3>
                <div className="space-y-1.5">
                  {detail.alerts.map((a) => (
                    <Link
                      key={a.alert_id}
                      to={`/alerts/${a.alert_id}`}
                      className="flex items-center gap-3 rounded-lg border border-slate-200 px-3 py-2 transition-colors hover:border-accent"
                    >
                      <BandBadge band={a.band} />
                      <span className="font-mono text-xs font-semibold text-primary">
                        AL-{String(a.alert_id).padStart(6, '0')}
                      </span>
                      <span className="ml-auto font-mono text-xs tabular-nums text-slate-500">
                        score {a.score}
                      </span>
                      <span className="text-[10px] text-accent">open →</span>
                    </Link>
                  ))}
                </div>
              </section>

              {/* recommendations */}
              {detail.recommendations.length > 0 && (
                <section>
                  <h3 className="mb-2 text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
                    Recommended next steps ({detail.band})
                  </h3>
                  <ul className="list-inside list-disc space-y-1 text-xs leading-relaxed text-slate-600">
                    {detail.recommendations.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                </section>
              )}

              {/* notes thread */}
              <section>
                <h3 className="mb-2 text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
                  Notes & audit trail ({detail.notes.length})
                </h3>
                <ol className="space-y-2">
                  {detail.notes.map((n) => (
                    <li
                      key={n.note_id}
                      className={`rounded-lg px-3 py-2 text-xs leading-relaxed ${
                        n.author === 'system'
                          ? 'border-l-2 border-accent/40 bg-slate-50 text-slate-500 italic'
                          : 'border border-slate-200 bg-white text-slate-700'
                      }`}
                    >
                      <div className="mb-0.5 flex items-baseline justify-between">
                        <span className="font-mono text-[10px] font-semibold not-italic text-slate-500">
                          {n.author}
                        </span>
                        <span className="font-mono text-[9px] text-slate-400 tabular-nums">
                          {dtFmt(n.ts)}
                        </span>
                      </div>
                      {n.body}
                    </li>
                  ))}
                </ol>
                {!closed && (
                  <div className="mt-3 flex gap-2">
                    <textarea
                      value={noteText}
                      onChange={(e) => setNoteText(e.target.value)}
                      rows={2}
                      placeholder={`Add audit note as ${detail.assignee ?? 'analyst'}…`}
                      className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-xs focus:border-accent focus:outline-none"
                    />
                    <button
                      onClick={submitNote}
                      disabled={busy || !noteText.trim()}
                      className="self-end rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-white hover:bg-primary-700 disabled:opacity-50"
                    >
                      Add
                    </button>
                  </div>
                )}
              </section>
            </div>

            {/* footer actions */}
            <div className="flex items-center gap-3 border-t border-slate-200 px-5 py-3">
              <button
                onClick={doExport}
                disabled={busy}
                className="rounded-lg bg-accent px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-accent-600 disabled:opacity-50"
              >
                ⤓ Export evidence ZIP
              </button>
              <span className="text-[10px] text-slate-400">
                PDF + JSON + 2 CSVs + README — opens offline, no tooling.
              </span>
            </div>
          </>
        ) : null}
      </aside>
    </>
  );
}

function TitleEditor({
  value,
  disabled,
  onSave,
}: {
  value: string;
  disabled: boolean;
  onSave: (title: string) => void;
}) {
  const [text, setText] = useState(value);
  const dirty = text.trim() !== '' && text !== value;
  return (
    <div className="flex items-start gap-2">
      <textarea
        value={text}
        rows={2}
        disabled={disabled}
        onChange={(e) => setText(e.target.value)}
        className="flex-1 rounded-lg border border-transparent px-2 py-1 text-sm font-semibold leading-snug text-primary hover:border-slate-200 focus:border-accent focus:outline-none disabled:text-slate-500"
      />
      {dirty && !disabled && (
        <button
          onClick={() => onSave(text.trim())}
          className="rounded-lg bg-accent px-3 py-1 text-xs font-semibold text-white"
        >
          Save
        </button>
      )}
    </div>
  );
}
