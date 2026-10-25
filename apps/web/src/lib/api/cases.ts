/** Cases resource (Phase 06) — mirrors routers/cases.py + routers/export.py. */
import { api } from '../http';
import type { AnalystOut, CaseBoard, CaseDetail, CaseStatus } from '../types';

export async function listCasesBoard(signal?: AbortSignal): Promise<CaseBoard> {
  const { data } = await api.get<CaseBoard>('/api/cases', { signal });
  return data;
}

export async function getCase(caseId: number, signal?: AbortSignal): Promise<CaseDetail> {
  const { data } = await api.get<CaseDetail>(`/api/cases/${caseId}`, { signal });
  return data;
}

export async function createCase(input: {
  alert_id: number;
  title?: string;
  assignee?: string;
}): Promise<CaseDetail> {
  const { data } = await api.post<CaseDetail>('/api/cases', input);
  return data;
}

export async function patchCase(
  caseId: number,
  patch: { title?: string; assignee?: string; status?: CaseStatus; actor?: string },
): Promise<CaseDetail> {
  const { data } = await api.patch<CaseDetail>(`/api/cases/${caseId}`, patch);
  return data;
}

export async function addCaseNote(
  caseId: number,
  note: { body: string; author?: string },
): Promise<{ note_id: number; case_id: number; notes_count: number }> {
  const { data } = await api.post(`/api/cases/${caseId}/notes`, note);
  return data;
}

export async function listAnalysts(signal?: AbortSignal): Promise<AnalystOut[]> {
  const { data } = await api.get<AnalystOut[]>('/api/analysts', { signal });
  return data;
}

/** Evidence ZIP — always POST (graph image optional); returns the file blob. */
export async function exportCaseZip(caseId: number, graphPng?: string): Promise<Blob> {
  const { data } = await api.post(
    `/api/cases/${caseId}/export`,
    { graph_png: graphPng ?? null },
    { responseType: 'blob', timeout: 120_000 },
  );
  return data as Blob;
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
