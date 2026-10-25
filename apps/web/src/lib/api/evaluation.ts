/** Evaluation harness API (Phase 07). */
import { api } from '../http';
import type { CompareReport, EvaluationReport, RunList } from '../types';

export async function listRuns(signal?: AbortSignal): Promise<RunList> {
  // analysis runs endpoint exists since Phase 02
  const { data } = await api.get<RunList>('/api/analysis/runs', { params: { limit: 50 }, signal });
  return data;
}

export async function getEvaluation(runId: number, signal?: AbortSignal): Promise<EvaluationReport> {
  const { data } = await api.get<EvaluationReport>(`/api/evaluation/${runId}`, { signal });
  return data;
}

export async function compareRuns(
  runA: number,
  runB: number,
  signal?: AbortSignal,
): Promise<CompareReport> {
  const { data } = await api.get<CompareReport>('/api/evaluation/compare', {
    params: { run_a: runA, run_b: runB },
    signal,
  });
  return data;
}

export async function rerunAnalysis(): Promise<{ run_id: number }> {
  const { data } = await api.post('/api/analysis/run');
  return data as { run_id: number };
}
