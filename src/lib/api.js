/**
 * Client for our own backend.
 *
 * Deliberately not the template's `src/lib/axios.js`: that instance is
 * built around a Bearer token in a header, and our session lives in an
 * httpOnly cookie the browser attaches by itself. There is no token for
 * JavaScript to hold, which is the point — an XSS bug cannot read a
 * cookie it cannot see.
 *
 * Every call goes to `/api/*` on this origin and is proxied to FastAPI by
 * the rewrite in next.config.mjs, so requests are same-origin and the
 * `SameSite=Lax` cookie is sent.
 */

const BASE = '/api';

export class ApiError extends Error {
  constructor(message, { status, code, body } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    /** Stable machine-readable code from the backend, e.g. 'ambiguous_account'. */
    this.code = code;
    this.body = body;
  }

  /** True when the session is missing or expired. */
  get isUnauthorized() {
    return this.status === 401;
  }

  /** True when the request never reached the server. */
  get isOffline() {
    return this.status === 0;
  }
}

function extractError(status, body) {
  // The backend returns either {code, message} or FastAPI's
  // {detail: {code, message}} / {detail: [validation errors]}.
  const detail = body?.detail ?? body;

  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    return {
      code: detail.code ?? 'error',
      message: detail.message ?? `Permintaan gagal (${status})`,
    };
  }

  if (Array.isArray(detail) && detail.length) {
    return { code: 'validation_error', message: detail[0]?.msg ?? 'Data tidak valid' };
  }

  return { code: 'error', message: `Permintaan gagal (${status})` };
}

async function request(path, { method = 'GET', body, headers = {}, signal } = {}) {
  let response;

  try {
    response = await fetch(`${BASE}${path}`, {
      method,
      signal,
      // Same-origin already sends cookies, but being explicit means this
      // keeps working if the base URL ever moves.
      credentials: 'same-origin',
      headers: {
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
        ...headers,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    if (error.name === 'AbortError') {
      throw error;
    }

    // Network failure. The PRD forbids implying anything was saved, so
    // this surfaces as an explicit offline error rather than a silent
    // empty result.
    throw new ApiError('Tidak ada koneksi ke server.', { status: 0, code: 'offline' });
  }

  if (response.status === 204) {
    return null;
  }

  const text = await response.text();
  let payload = null;

  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    const { code, message } = extractError(response.status, payload);
    throw new ApiError(message, { status: response.status, code, body: payload });
  }

  return payload;
}

export const api = {
  get: (path, options) => request(path, { ...options, method: 'GET' }),
  post: (path, body, options) => request(path, { ...options, method: 'POST', body }),
  patch: (path, body, options) => request(path, { ...options, method: 'PATCH', body }),
};

// ----------------------------------------------------------------------
// Endpoints
// ----------------------------------------------------------------------

export const authApi = {
  me: () => api.get('/auth/me'),
  login: (email, password) => api.post('/auth/login', { email, password }),
  register: (email, password) => api.post('/auth/register', { email, password }),
  logout: () => api.post('/auth/logout'),
};

export const accountsApi = {
  list: () => api.get('/accounts'),
  create: (payload) => api.post('/accounts', payload),
  summary: () => api.get('/summary'),
};

export const transactionsApi = {
  list: (limit = 50) => api.get(`/transactions?limit=${limit}`),
  preview: (draft) => api.post('/transactions/preview', draft),
};

export const chatApi = {
  messages: () => api.get('/chat/messages'),
  send: (body, { signal } = {}) => api.post('/chat/messages', { body }, { signal }),
  confirmDraft: (id) => api.post(`/chat/drafts/${id}/confirm`),
  cancelDraft: (id) => api.post(`/chat/drafts/${id}/cancel`),
};
