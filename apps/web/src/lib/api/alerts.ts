/** Alerts resource — typed calls mirroring app/routers/alerts.py. */
import { api } from '../http';
import type {
  AlertDetail,
  AlertPage,
  AlertStatus,
  Band,
  TimelineResponse,
} from '../types';

export interface AlertListParams {
  band?: Band;
  status?: AlertStatus;
  rule?: string;
  entity?: number;
  limit?: number;
  offset?: number;
  signal?: AbortSignal;
}

export async function listAlerts(params: AlertListParams): Promise<AlertPage> {
  const { signal, ...query } = params;
  const { data } = await api.get<AlertPage>('/api/alerts', {
    signal,
    params: Object.fromEntries(
      Object.entries(query).filter(([, v]) => v !== undefined && v !== null && v !== ''),
    ),
  });
  return data;
}

export async function getAlert(alertId: number, signal?: AbortSignal): Promise<AlertDetail> {
  const { data } = await api.get<AlertDetail>(`/api/alerts/${alertId}`, { signal });
  return data;
}

export async function patchAlertStatus(
  alertId: number,
  status: AlertStatus,
): Promise<AlertDetail> {
  const { data } = await api.patch<AlertDetail>(`/api/alerts/${alertId}/status`, { status });
  return data;
}

export async function getTimeline(alertId: number, signal?: AbortSignal): Promise<TimelineResponse> {
  const { data } = await api.get<TimelineResponse>(`/api/timeline/${alertId}`, { signal });
  return data;
}
