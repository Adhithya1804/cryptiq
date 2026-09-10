import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ApiError } from '@/types/common';
import { request, toApiError } from './http';
import { HttpError } from './errors';

const asError = (cause: unknown): ApiError => toApiError(cause);

/** Build a `Response`-like object good enough for `request()`. */
function jsonResponse(body: unknown, init: { status?: number; ok?: boolean } = {}) {
  const status = init.status ?? 200;
  return {
    ok: init.ok ?? (status >= 200 && status < 300),
    status,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: () => Promise.resolve(body),
  } as unknown as Response;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('request() error normalisation', () => {
  it("reads Cryptiq's nested { error: { code, message } } envelope", async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse({ error: { code: 'not_found', message: 'No inspection with id "x".' } }, { status: 404 }))),
    );

    const error = await request<never>('/inspections/x').catch(asError);

    expect(error).toMatchObject({
      message: 'No inspection with id "x".',
      status: 404,
      code: 'not_found',
    });
  });

  it('still reads a flat { message, code } body', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse({ message: 'flat', code: 'flat_code' }, { status: 409 }))),
    );

    const error = await request<never>('/x').catch(asError);
    expect(error).toMatchObject({ message: 'flat', status: 409, code: 'flat_code' });
  });

  it('falls back to a status message when the body carries nothing useful', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({}, { status: 404 }))));

    await expect(request('/x')).rejects.toBeInstanceOf(HttpError);
    const error = await request<never>('/x').catch(asError);
    expect(error.message).toBe('The requested resource was not found.');
  });

  it('surfaces a network failure as a retryable connection error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    );

    const error = await request<never>('/x').catch(asError);
    expect(error.network).toBe(true);
  });

  it('decodes a successful JSON body', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({ items: [1, 2, 3] }))));
    await expect(request<{ items: number[] }>('/x')).resolves.toEqual({ items: [1, 2, 3] });
  });
});
