/**
 * Single API entry point (prompt pitfall P3: this is the ONLY data path).
 * baseURL '' = same-origin; the vite dev proxy forwards /api + /health to :8000,
 * so the browser never needs to know where the API runs. Override with
 * VITE_API_URL when you want to hit a different host directly.
 */
import axios, { AxiosError } from 'axios';
import toast from 'react-hot-toast';

import { isApiErrorShape, type HealthResponse } from './types';

const baseURL: string = import.meta.env.VITE_API_URL ?? '';

export const api = axios.create({ baseURL, timeout: 30_000 });

if (import.meta.env.DEV) {
  api.interceptors.request.use((cfg) => {
    console.debug(`[api] → ${cfg.method?.toUpperCase()} ${cfg.baseURL}${cfg.url}`);
    return cfg;
  });
}

/** Normalize every failure into Error(message) using the backend error model
 * and surface a toast — pages still get their ErrorState for retry UX. */
api.interceptors.response.use(undefined, (error: AxiosError) => {
  if (axios.isCancel(error) || error.code === 'ERR_CANCELED') {
    return Promise.reject(error);
  }
  const data = error.response?.data;
  const message = isApiErrorShape(data) ? `${data.error.code}: ${data.error.message}` : error.message;
  toast.error(message);
  return Promise.reject(new Error(message));
});

export interface HealthResult extends HealthResponse {
  latencyMs: number;
}

export async function getHealth(signal?: AbortSignal): Promise<HealthResult> {
  const started = performance.now();
  const { data } = await api.get<HealthResponse>('/health', { signal });
  return { ...data, latencyMs: Math.round(performance.now() - started) };
}
