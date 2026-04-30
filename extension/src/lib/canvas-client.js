/**
 * Shared Canvas client for browser-facing code.
 *
 * This is the extension-side equivalent of a lightweight SDK layer:
 * - centralizes Canvas base URL + auth handling
 * - exposes domain methods instead of scattered fetch calls
 * - keeps popup/background logic thin
 */

import { getSetting, setSetting } from './cache.js';

const DEFAULT_BASE_URL = 'https://canvas.vt.edu';
const API_PREFIX = '/api/v1';

function stripTrailingSlash(value) {
  return String(value || DEFAULT_BASE_URL).replace(/\/+$/, '');
}

export class CanvasClient {
  constructor({ baseUrl = DEFAULT_BASE_URL, tokenStore = getSetting, tokenWriter = setSetting } = {}) {
    this.baseUrl = stripTrailingSlash(baseUrl);
    this.tokenStore = tokenStore;
    this.tokenWriter = tokenWriter;
  }

  async getToken() {
    const stored = await this.tokenStore('canvas_token', 'settings');
    return stored?.value ?? null;
  }

  async setToken(token) {
    const normalized = token?.trim() || null;
    await this.tokenWriter(normalized, 'canvas_token', 'settings');
    return normalized;
  }

  async clearToken() {
    await this.tokenWriter(null, 'canvas_token', 'settings');
  }

  buildUrl(path, params = null) {
    const url = new URL(`${this.baseUrl}${API_PREFIX}${path}`);
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value === undefined || value === null || value === '') return;
        url.searchParams.set(key, String(value));
      });
    }
    return url.toString();
  }

  async request(path, { method = 'GET', params = null, headers = {}, body = undefined } = {}) {
    const token = await this.getToken();
    if (!token) throw new Error('Not authenticated');

    const response = await fetch(this.buildUrl(path, params), {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/json',
        ...headers,
      },
      body,
    });

    if (response.status === 401) {
      await this.clearToken();
      throw new Error('Token expired');
    }

    if (!response.ok) {
      throw new Error(`Canvas API error: ${response.status}`);
    }

    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      return response.json();
    }
    return response.text();
  }

  async validateToken() {
    const profile = await this.request('/users/self');
    return {
      ok: true,
      user: profile,
    };
  }

  async getUpcomingAssignments({ perPage = 20 } = {}) {
    return this.request('/users/self/upcoming_events', {
      params: { per_page: perPage },
    });
  }

  async getCourses({ perPage = 100, enrollmentState = 'active' } = {}) {
    return this.request('/courses', {
      params: {
        per_page: perPage,
        enrollment_state: enrollmentState,
      },
    });
  }

  async getCourseAssignments(courseId, { perPage = 50 } = {}) {
    return this.request(`/courses/${courseId}/assignments`, {
      params: { per_page: perPage },
    });
  }
}

export function createCanvasClient(options = {}) {
  return new CanvasClient(options);
}
