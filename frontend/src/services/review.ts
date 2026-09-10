/**
 * Review queue — findings awaiting a human disposition.
 *
 * The paginated, server-filtered client lives in `client.ts` (`getReviewQueue`,
 * `updateReviewItem`). This wrapper keeps the flat "all items" shape a couple of
 * callers still use.
 */

import type { ReviewQueueItem } from '@/types/domain';
import { getReviewQueue } from './client';

export async function fetchReviewQueue(signal?: AbortSignal): Promise<ReviewQueueItem[]> {
  const pageSize = 200;
  const first = await getReviewQueue({ page: 1, pageSize, ...(signal ? { signal } : {}) });
  const items = [...first.items];
  for (let page = 2; page <= first.pages; page += 1) {
    const next = await getReviewQueue({ page, pageSize, ...(signal ? { signal } : {}) });
    items.push(...next.items);
  }
  return items;
}
