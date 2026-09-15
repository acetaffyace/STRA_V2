import { apiFetch, apiUrl } from '@/lib/api';
import type { CollectionWindow, CollectReviewsResponse, SamplingContract } from '@/types/acquisition';

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = '';
    try {
      const body = await response.json();
      detail = typeof body?.detail === 'string' ? body.detail : JSON.stringify(body?.detail ?? body);
    } catch {
      detail = await response.text().catch(() => '');
    }
    throw new Error(detail || `Request failed with status ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function collectReviews(
  sampling: SamplingContract,
  options: { force?: boolean } = {},
): Promise<CollectReviewsResponse> {
  const response = await apiFetch(apiUrl('/reviews/collect'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sampling, force: options.force ?? true }),
  });
  return handleResponse<CollectReviewsResponse>(response);
}

export async function fetchCollectionWindows(appId?: number): Promise<CollectionWindow[]> {
  const url = new URL(apiUrl('/reviews/collection-windows'), typeof window !== 'undefined' ? window.location.origin : 'http://localhost');
  if (appId != null) url.searchParams.set('app_id', String(appId));
  const response = await apiFetch(url.toString(), { cache: 'no-store' });
  const payload = await handleResponse<{ app_id?: number | null; items: CollectionWindow[] }>(response);
  return payload.items ?? [];
}
