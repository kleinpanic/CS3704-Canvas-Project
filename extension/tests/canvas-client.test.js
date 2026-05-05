/**
 * Unit tests for canvas-client.js
 *
 * Mocks:
 *  - cache.js (getSetting / setSetting) via jest.mock
 *  - global fetch via jest.fn()
 */

// We need to mock the cache module before importing canvas-client
jest.mock('../src/lib/cache.js', () => ({
  getSetting: jest.fn(),
  setSetting: jest.fn(),
}));

import { CanvasClient, createCanvasClient } from '../src/lib/canvas-client.js';
import { getSetting, setSetting } from '../src/lib/cache.js';

// ── helpers ───────────────────────────────────────────────────────────────────

function makeFetchResponse({ status = 200, ok = true, json = null, text = '', contentType = 'application/json' } = {}) {
  return {
    status,
    ok,
    headers: { get: () => contentType },
    json: jest.fn().mockResolvedValue(json),
    text: jest.fn().mockResolvedValue(text),
  };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('stripTrailingSlash (via CanvasClient constructor)', () => {
  test('removes a single trailing slash', () => {
    const client = new CanvasClient({ baseUrl: 'https://canvas.vt.edu/' });
    expect(client.baseUrl).toBe('https://canvas.vt.edu');
  });

  test('removes multiple trailing slashes', () => {
    const client = new CanvasClient({ baseUrl: 'https://canvas.vt.edu///' });
    expect(client.baseUrl).toBe('https://canvas.vt.edu');
  });

  test('leaves URL unchanged when no trailing slash', () => {
    const client = new CanvasClient({ baseUrl: 'https://canvas.vt.edu' });
    expect(client.baseUrl).toBe('https://canvas.vt.edu');
  });

  test('falls back to DEFAULT_BASE_URL when baseUrl is falsy', () => {
    const client = new CanvasClient({ baseUrl: '' });
    expect(client.baseUrl).toBe('https://canvas.vt.edu');
  });
});

describe('CanvasClient.buildUrl', () => {
  let client;

  beforeEach(() => {
    client = new CanvasClient({ baseUrl: 'https://canvas.vt.edu' });
  });

  test('constructs URL without params', () => {
    const url = client.buildUrl('/courses');
    expect(url).toBe('https://canvas.vt.edu/api/v1/courses');
  });

  test('constructs URL with params', () => {
    const url = client.buildUrl('/courses', { per_page: '50', enrollment_state: 'active' });
    const parsed = new URL(url);
    expect(parsed.searchParams.get('per_page')).toBe('50');
    expect(parsed.searchParams.get('enrollment_state')).toBe('active');
  });

  test('skips null param values', () => {
    const url = client.buildUrl('/courses', { per_page: 50, bad: null });
    const parsed = new URL(url);
    expect(parsed.searchParams.has('bad')).toBe(false);
    expect(parsed.searchParams.get('per_page')).toBe('50');
  });

  test('skips undefined param values', () => {
    const url = client.buildUrl('/courses', { per_page: 50, bad: undefined });
    const parsed = new URL(url);
    expect(parsed.searchParams.has('bad')).toBe(false);
  });

  test('skips empty-string param values', () => {
    const url = client.buildUrl('/courses', { per_page: 50, empty: '' });
    const parsed = new URL(url);
    expect(parsed.searchParams.has('empty')).toBe(false);
  });

  test('handles nested path segments', () => {
    const url = client.buildUrl('/courses/123/assignments', { per_page: 25 });
    expect(url).toContain('/api/v1/courses/123/assignments');
  });
});

describe('CanvasClient.request', () => {
  let client;
  let mockFetch;

  beforeEach(() => {
    getSetting.mockReset();
    setSetting.mockReset();

    client = new CanvasClient({
      baseUrl: 'https://canvas.vt.edu',
      tokenStore: getSetting,
      tokenWriter: setSetting,
    });

    mockFetch = jest.fn();
    global.fetch = mockFetch;
  });

  afterEach(() => {
    delete global.fetch;
  });

  test('throws "Not authenticated" when no token is stored', async () => {
    getSetting.mockResolvedValue(null);
    await expect(client.request('/courses')).rejects.toThrow('Not authenticated');
    expect(mockFetch).not.toHaveBeenCalled();
  });

  test('throws "Not authenticated" when stored record has null value', async () => {
    getSetting.mockResolvedValue({ value: null });
    await expect(client.request('/courses')).rejects.toThrow('Not authenticated');
  });

  test('calls fetch with correct Authorization header', async () => {
    getSetting.mockResolvedValue({ value: 'my-test-token' });
    const fakeData = { id: 1, name: 'Test User' };
    mockFetch.mockResolvedValue(makeFetchResponse({ json: fakeData }));

    const result = await client.request('/users/self');
    expect(mockFetch).toHaveBeenCalledTimes(1);

    const [, options] = mockFetch.mock.calls[0];
    expect(options.headers.Authorization).toBe('Bearer my-test-token');
    expect(options.headers.Accept).toBe('application/json');
    expect(result).toEqual(fakeData);
  });

  test('passes method and body to fetch', async () => {
    getSetting.mockResolvedValue({ value: 'tok' });
    mockFetch.mockResolvedValue(makeFetchResponse({ json: {} }));

    await client.request('/courses', { method: 'POST', body: '{"name":"X"}' });
    const [, options] = mockFetch.mock.calls[0];
    expect(options.method).toBe('POST');
    expect(options.body).toBe('{"name":"X"}');
  });

  test('throws "Token expired" on 401 and clears the token', async () => {
    getSetting.mockResolvedValue({ value: 'expired-token' });
    mockFetch.mockResolvedValue(makeFetchResponse({ status: 401, ok: false }));

    await expect(client.request('/courses')).rejects.toThrow('Token expired');

    // clearToken calls tokenWriter(null, 'canvas_token', 'settings')
    expect(setSetting).toHaveBeenCalledWith(null, 'canvas_token', 'settings');
  });

  test('throws Canvas API error on non-401 error status', async () => {
    getSetting.mockResolvedValue({ value: 'tok' });
    mockFetch.mockResolvedValue(makeFetchResponse({ status: 500, ok: false }));

    await expect(client.request('/courses')).rejects.toThrow('Canvas API error: 500');
  });

  test('returns text when content-type is not application/json', async () => {
    getSetting.mockResolvedValue({ value: 'tok' });
    mockFetch.mockResolvedValue(makeFetchResponse({ contentType: 'text/plain', text: 'hello', json: null }));

    const result = await client.request('/some/text/endpoint');
    expect(result).toBe('hello');
  });
});

describe('CanvasClient.setToken / clearToken', () => {
  let client;

  beforeEach(() => {
    getSetting.mockReset();
    setSetting.mockReset();
    setSetting.mockResolvedValue(undefined);
    client = new CanvasClient({ tokenStore: getSetting, tokenWriter: setSetting });
  });

  test('setToken trims whitespace and stores token', async () => {
    const result = await client.setToken('  mytoken  ');
    expect(result).toBe('mytoken');
    expect(setSetting).toHaveBeenCalledWith('mytoken', 'canvas_token', 'settings');
  });

  test('setToken returns null for empty/whitespace-only input', async () => {
    const result = await client.setToken('   ');
    expect(result).toBeNull();
    expect(setSetting).toHaveBeenCalledWith(null, 'canvas_token', 'settings');
  });

  test('setToken returns null for null input', async () => {
    const result = await client.setToken(null);
    expect(result).toBeNull();
  });

  test('clearToken writes null', async () => {
    await client.clearToken();
    expect(setSetting).toHaveBeenCalledWith(null, 'canvas_token', 'settings');
  });
});

describe('CanvasClient domain methods', () => {
  let client;
  let mockFetch;

  beforeEach(() => {
    getSetting.mockReset();
    setSetting.mockReset();
    getSetting.mockResolvedValue({ value: 'test-token' });

    client = new CanvasClient({
      baseUrl: 'https://canvas.vt.edu',
      tokenStore: getSetting,
      tokenWriter: setSetting,
    });

    mockFetch = jest.fn().mockResolvedValue({
      status: 200,
      ok: true,
      headers: { get: () => 'application/json' },
      json: jest.fn().mockResolvedValue([]),
      text: jest.fn().mockResolvedValue(''),
    });
    global.fetch = mockFetch;
  });

  afterEach(() => {
    delete global.fetch;
  });

  test('getCurrentUser calls /users/self', async () => {
    mockFetch.mockResolvedValue({
      status: 200, ok: true,
      headers: { get: () => 'application/json' },
      json: jest.fn().mockResolvedValue({ id: 1, name: 'Test' }),
      text: jest.fn(),
    });
    const result = await client.getCurrentUser();
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain('/api/v1/users/self');
    expect(result).toEqual({ id: 1, name: 'Test' });
  });

  test('validateToken returns ok:true with user profile', async () => {
    const profile = { id: 42, name: 'Alice' };
    mockFetch.mockResolvedValue({
      status: 200, ok: true,
      headers: { get: () => 'application/json' },
      json: jest.fn().mockResolvedValue(profile),
      text: jest.fn(),
    });
    const result = await client.validateToken();
    expect(result).toEqual({ ok: true, user: profile });
  });

  test('getUpcomingAssignments calls upcoming_events with per_page', async () => {
    await client.getUpcomingAssignments({ perPage: 10 });
    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain('/users/self/upcoming_events');
    expect(url).toContain('per_page=10');
  });

  test('getDashboardCards calls dashboard_cards', async () => {
    await client.getDashboardCards();
    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain('/dashboard/dashboard_cards');
  });

  test('getCourses calls /courses with include[]=teachers', async () => {
    await client.getCourses();
    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain('/courses');
    expect(url).toContain('enrollment_state=active');
  });

  test('getCourseAssignments calls courses/:id/assignments', async () => {
    await client.getCourseAssignments(123, { perPage: 30 });
    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain('/courses/123/assignments');
    expect(url).toContain('per_page=30');
  });

  test('getCourseModules calls courses/:id/modules', async () => {
    await client.getCourseModules(456);
    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain('/courses/456/modules');
  });

  test('getCourseFiles calls courses/:id/files', async () => {
    await client.getCourseFiles(789);
    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain('/courses/789/files');
  });

  test('getCourseAnnouncements calls /announcements with context_codes', async () => {
    await client.getCourseAnnouncements(101);
    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain('/announcements');
    expect(url).toContain('course_101');
  });
});

describe('createCanvasClient factory', () => {
  test('returns a CanvasClient instance', () => {
    const client = createCanvasClient();
    expect(client).toBeInstanceOf(CanvasClient);
  });
});
