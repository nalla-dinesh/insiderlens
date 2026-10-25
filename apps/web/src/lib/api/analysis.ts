/** Analysis runs resource — POST run + runs list. */
import { api } from '../http';
import type { AnalysisReport, RunList } from '../types';

export async function runAnalysis(): Promise<AnalysisReport> {
  const { data } = await api.post<AnalysisReport>('/api/analysis/run', undefined, {
    timeout: 120_000, // a full 14-rule run takes seconds on the seeded bundle
  });
  return data;
}

export async function listRuns(limit = 5, signal?: AbortSignal): Promise<RunList> {
  const { data } = await api.get<RunList>('/api/analysis/runs', {
    signal,
    params: { limit },
  });
  return data;
}
