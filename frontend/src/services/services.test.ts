import { describe, expect, it } from 'vitest';
import {
  NO_BACKEND_MESSAGE,
  fetchHistory,
  fetchProjects,
  fetchReviewQueue,
  isBackendConfigured,
  submitInspection,
} from './index';
import { toApiError } from './http';
import { HttpError } from './errors';

describe('service layer with no backend configured', () => {
  it('reports the backend as unconfigured', () => {
    expect(isBackendConfigured()).toBe(false);
  });

  it('resolves read collections to empty arrays', async () => {
    await expect(fetchProjects()).resolves.toEqual([]);
    await expect(fetchHistory()).resolves.toEqual([]);
    await expect(fetchReviewQueue()).resolves.toEqual([]);
  });

  it('rejects the inspection submit with a connection error instead of fabricating a result', async () => {
    await expect(
      submitInspection({ repositoryUrl: 'https://github.com/pyca/cryptography', commitSha: 'a'.repeat(40) }),
    ).rejects.toMatchObject({ message: NO_BACKEND_MESSAGE, network: true });
  });
});

describe('toApiError', () => {
  it('preserves HttpError fields', () => {
    const error = toApiError(new HttpError({ message: 'boom', status: 404, code: 'not_found' }));
    expect(error).toEqual({ message: 'boom', status: 404, code: 'not_found' });
  });

  it('falls back to a generic message for unknown throwables', () => {
    expect(toApiError('weird')).toEqual({ message: 'Something went wrong. Please try again.' });
  });
});
