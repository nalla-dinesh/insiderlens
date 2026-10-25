/** Explorer resource — account ego graphs (Phase 02 endpoint). */
import { api } from '../http';
import type { EgoGraphResponse } from '../types';

export async function getEgoGraph(
  accId: number,
  depth: 1 | 2,
  signal?: AbortSignal,
): Promise<EgoGraphResponse> {
  const { data } = await api.get<EgoGraphResponse>(`/api/graph/ego/${accId}`, {
    signal,
    params: { depth },
  });
  return data;
}
