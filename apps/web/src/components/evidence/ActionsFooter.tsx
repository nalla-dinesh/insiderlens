/** Actions footer — case loop closure:
 *  - PATCH status stays as-is (alert queue semantics)
 *  - "Convert to case" opens a preflight modal (prefilled title + analyst
 *    assignee select) → POST /api/cases → toast + navigate to the case drawer
 *  - "Export evidence" snapshots the live Cytoscape canvas (cy.png) and pulls
 *    the case ZIP; >20MB dataURL guard → exports without the image + notice
 *    Disabled hard with WHY-tooltips when the alert isn't case-linked yet. */
import { useState } from 'react';
import toast from 'react-hot-toast';
import { useNavigate } from 'react-router-dom';
import type { Core } from 'cytoscape';

import { patchAlertStatus } from '../../lib/api/alerts';
import {
  createCase,
  downloadBlob,
  exportCaseZip,
  listAnalysts,
} from '../../lib/api/cases';
import { useApi } from '../../lib/hooks';
import { STATUSES, type AlertStatus, type AnalystOut, type Band } from '../../lib/types';

const PNG_GUARD_CHARS = 20_000_000; // ≈ 20MB dataURL — beyond this we export without the image

export default function ActionsFooter({
  alertId,
  status,
  onChanged,
  caseId,
  cy,
  band,
  topReason,
  entityCount,
}: {
  alertId: number;
  status: AlertStatus;
  onChanged: (next: AlertStatus) => void;
  caseId: number | null;
  cy: Core | null;
  band: Band;
  topReason: string;
  entityCount: number;
}) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);

  const change = async (next: AlertStatus) => {
    if (next === status || busy) return;
    setBusy(true);
    try {
      const updated = await patchAlertStatus(alertId, next);
      onChanged(updated.status);
      toast.success(`Alert #${alertId} → ${updated.status}`);
    } catch {
      /* interceptor toasts */
    } finally {
      setBusy(false);
    }
  };

  const doExport = async () => {
    if (!caseId || busy) return;
    setBusy(true);
    try {
      let dataUrl: string | undefined;
      try {
        dataUrl = cy?.png({ full: true, scale: 2, output: 'base64uri' }) as string | undefined;
      } catch {
        dataUrl = undefined; // webgl-less / canvas tainted → text adjacency fallback
      }
      if (dataUrl && dataUrl.length > PNG_GUARD_CHARS) {
        dataUrl = undefined;
        toast('Graph snapshot too large — exporting with the text adjacency fallback.', {
          icon: 'ℹ️',
        });
      }
      const blob = await exportCaseZip(caseId, dataUrl);
      downloadBlob(blob, `case_${caseId}_evidence.zip`);
      toast.success(`case_${caseId}_evidence.zip downloaded`);
    } catch {
      /* interceptor toasts */
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <label className="flex items-center gap-2">
        <span className="text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
          Status
        </span>
        <select
          value={status}
          disabled={busy}
          onChange={(e) => void change(e.target.value as AlertStatus)}
          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-primary focus:border-accent focus:outline-none disabled:opacity-50"
        >
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>

      {caseId ? (
        <button
          onClick={() => navigate(`/cases?focus=${caseId}`)}
          className="rounded-lg border border-accent bg-accent-100 px-4 py-1.5 text-sm font-semibold text-accent transition-colors hover:bg-accent hover:text-white"
        >
          Open case #{caseId} →
        </button>
      ) : (
        <button
          onClick={() => setModalOpen(true)}
          title="Convert this alert into a tracked case (carries full evidence)"
          className="rounded-lg bg-primary px-4 py-1.5 text-sm font-semibold text-white transition-colors hover:bg-primary-700"
        >
          Convert to case
        </button>
      )}

      <button
        onClick={doExport}
        disabled={!caseId || busy}
        title={
          caseId
            ? 'Download case evidence bundle (ZIP: pdf + json + csvs)'
            : 'Convert to a case first — export bundles are case-scoped'
        }
        className={`rounded-lg px-4 py-1.5 text-sm font-medium transition-colors ${
          caseId
            ? 'border border-slate-200 text-slate-700 hover:border-accent hover:text-accent'
            : 'cursor-not-allowed border border-slate-200 text-slate-400'
        }`}
      >
        ⤓ Export evidence{caseId ? '' : ' (needs case)'}
      </button>

      {busy && <span className="text-xs text-slate-400">working…</span>}

      {modalOpen && (
        <ConvertModal
          alertId={alertId}
          band={band}
          topReason={topReason}
          entityCount={entityCount}
          onClose={() => setModalOpen(false)}
          onCreated={(newCaseId) => {
            setModalOpen(false);
            toast.success(`Case #${newCaseId} created from alert AL-${String(alertId).padStart(6, '0')}`);
            navigate(`/cases?focus=${newCaseId}`);
          }}
        />
      )}
    </section>
  );
}

function ConvertModal({
  alertId,
  band,
  topReason,
  entityCount,
  onClose,
  onCreated,
}: {
  alertId: number;
  band: Band;
  topReason: string;
  entityCount: number;
  onClose: () => void;
  onCreated: (caseId: number) => void;
}) {
  const cleanReason = topReason.replace(/^\[[A-Z0-9]+\]\s*/, '');
  const [title, setTitle] = useState(`[${band}] ${cleanReason} · ${entityCount} entities`);
  const [assignee, setAssignee] = useState('');
  const [saving, setSaving] = useState(false);
  const fetcher = (signal: AbortSignal) => listAnalysts(signal);
  const { data: analysts } = useApi<AnalystOut[]>(fetcher, []);

  const submit = async () => {
    setSaving(true);
    try {
      const created = await createCase({
        alert_id: alertId,
        title: title.trim() || undefined,
        assignee: assignee || undefined,
      });
      onCreated(created.case_id);
    } catch (e) {
      if ((e as { response?: { status?: number } }).response?.status === 409) {
        onClose();
        toast.error('This alert already belongs to an open case.');
      } else {
        toast.error(`Could not create case: ${(e as Error).message}`);
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-primary/50 p-4 backdrop-blur-[1px]">
      <div className="w-full max-w-lg rounded-xl border border-slate-200 bg-white p-5 shadow-2xl">
        <h3 className="text-sm font-bold text-primary">Convert alert to case</h3>
        <p className="mt-0.5 text-xs text-slate-500">
          Carries full evidence (reasons, thresholds, timeline, graph) into a tracked
          investigation. One alert = one open case at a time.
        </p>

        <label className="mt-4 block">
          <span className="text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
            Case title
          </span>
          <textarea
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            rows={3}
            maxLength={200}
            className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-accent focus:outline-none"
          />
        </label>

        <label className="mt-3 block">
          <span className="text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
            Assign to analyst
          </span>
          <select
            value={assignee}
            onChange={(e) => setAssignee(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:border-accent focus:outline-none"
          >
            <option value="">— assign later</option>
            {(analysts ?? []).map((a) => (
              <option key={a.emp_id} value={a.name}>
                {a.name} · {a.role} ({a.branch})
              </option>
            ))}
          </select>
        </label>

        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:border-slate-300"
          >
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={saving}
            className="rounded-lg bg-accent px-5 py-2 text-sm font-semibold text-white hover:bg-accent-600 disabled:opacity-50"
          >
            {saving ? 'Creating…' : 'Create case'}
          </button>
        </div>
      </div>
    </div>
  );
}
