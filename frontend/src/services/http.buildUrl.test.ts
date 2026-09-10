import { afterEach, describe, expect, it, vi } from 'vitest';

// Regression: a same-origin deployment builds with VITE_API_BASE_URL=/api/v1
// (a relative path). `new URL(x, base)` rejects a non-absolute `base`, so
// buildUrl() must resolve a relative base against window.location.origin
// instead of passing it straight through — otherwise every request throws
// "Invalid URL" and surfaces as "Could not reach the Cryptiq service".
vi.mock('./config', () => ({
  apiConfig: { baseUrl: '/api/v1', timeoutMs: 20_000 },
  isBackendConfigured: () => true,
  assertBackendConfigured: () => undefined,
  NO_BACKEND_MESSAGE: '',
}));

let lastUrl = '';

function okJson() {
  return {
    ok: true,
    status: 200,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: () => Promise.resolve({}),
  } as unknown as Response;
}

afterEach(() => {
  vi.restoreAllMocks();
  lastUrl = '';
});

describe('buildUrl with a relative (same-origin) API base', () => {
  it('resolves /api/v1 against the page origin instead of throwing', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: string) => {
        lastUrl = input;
        return Promise.resolve(okJson());
      }),
    );

    const { request } = await import('./http');
    await request('/scans', { method: 'POST', body: { repository_url: 'x', commit_sha: 'y' } });

    expect(lastUrl).toMatch(/^https?:\/\//);
    expect(lastUrl).toBe(`${window.location.origin}/api/v1/scans`);
  });

  it('applies query params on top of the resolved same-origin URL', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: string) => {
        lastUrl = input;
        return Promise.resolve(okJson());
      }),
    );

    const { request } = await import('./http');
    await request('/scans/abc/findings', { query: { page: 1, page_size: 50 } });

    const url = new URL(lastUrl);
    expect(url.origin).toBe(window.location.origin);
    expect(url.pathname).toBe('/api/v1/scans/abc/findings');
    expect(url.searchParams.get('page')).toBe('1');
    expect(url.searchParams.get('page_size')).toBe('50');
  });
});
