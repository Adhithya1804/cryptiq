/**
 * The one error type the API layer throws. Kept in its own module so both
 * `http.ts` and `config.ts` can construct it without an import cycle.
 */

import type { ApiError } from '@/types/common';

export class HttpError extends Error implements ApiError {
  readonly code?: string;
  readonly status?: number;
  readonly network?: boolean;

  constructor(error: ApiError) {
    super(error.message);
    this.name = 'HttpError';
    if (error.code !== undefined) this.code = error.code;
    if (error.status !== undefined) this.status = error.status;
    if (error.network !== undefined) this.network = error.network;
  }
}
