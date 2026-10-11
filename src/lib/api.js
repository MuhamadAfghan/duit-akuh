/**
 * Client for our own backend.
 *
 * Deliberately not the template's `src/lib/axios.js`: that instance is
 * built around a Bearer token in a header, and our session lives in an
 * httpOnly cookie the browser attaches by itself. There is no token for
 * JavaScript to hold, which is the point — an XSS bug cannot read a
 * cookie it cannot see.
 *
 * Every call goes to `/srv/*` on this origin and is proxied to FastAPI by
 * the rewrite in next.config.mjs, so requests are same-origin and the
 * `SameSite=Lax` cookie is sent.
 *
 * The prefix is `/srv`, not the obvious `/api`, because content blockers
 * ship rules that match on path. We watched an extension kill
 * `fetch('/api/auth/me')`, `/api/accounts` and `/api/chat/messages`
 * before they left the browser — `TypeError: Failed to fetch`, no
 * request on the wire — while `/api/summary` and `/api/auth/me?x=1` went
 * through untouched. That is pattern matching on the path, and we cannot
 * fix someone else's filter list. Moving off `/api` sidesteps the whole
 * class of rule. Change this and you must change the rewrite in
 * next.config.mjs and NEVER_CACHE_PREFIXES in public/sw.js with it.
 */

const BASE = '/srv';

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
  put: (path, body, options) => request(path, { ...options, method: 'PUT', body }),
  patch: (path, body, options) => request(path, { ...options, method: 'PATCH', body }),
  del: (path, options) => request(path, { ...options, method: 'DELETE' }),
};

// ----------------------------------------------------------------------
// Endpoints
// ----------------------------------------------------------------------

export const authApi = {
  me: () => api.get('/auth/me'),
  login: (email, password) => api.post('/auth/login', { email, password }),
  register: (email, password) => api.post('/auth/register', { email, password }),
  logout: () => api.post('/auth/logout'),

  /**
   * Always resolves for a well-formed address, registered or not. The
   * backend answers 202 either way on purpose, so there is nothing here
   * to branch on and nothing to tell the user beyond "check your mail".
   */
  forgotPassword: (email) => api.post('/auth/forgot-password', { email }),

  resetPassword: (token, newPassword) =>
    api.post('/auth/reset-password', { token, new_password: newPassword }),
};

export const accountsApi = {
  list: () => api.get('/accounts'),
  create: (payload) => api.post('/accounts', payload),
  summary: () => api.get('/summary'),
};

export const goalsApi = {
  /** `remainingDeposits` drives the per-deposit figure; 0 means unscheduled. */
  list: (remainingDeposits = 0) => api.get(`/goals?remaining_deposits=${remainingDeposits}`),

  /**
   * The FR11 options for reaching a goal on a given monthly capacity:
   * more deposits, more up front, or more per period.
   */
  plan: (id, capacity) => api.get(`/goals/${id}/plan?capacity=${capacity}`),
};

export const budgetsApi = {
  list: (period = 'bulan_ini') => api.get(`/budgets?period=${period}`),

  /** Creates or replaces one category's monthly limit. */
  set: (category, amount) => api.put('/budgets', { category, amount }),

  remove: (category) => api.del(`/budgets?category=${encodeURIComponent(category)}`),
};

/**
 * Simulations change nothing until a plan is applied (AC07), so none of
 * these need a confirmation card.
 */
export const simulationsApi = {
  saving: (payload) => api.post('/simulations/saving', payload),
  deposit: (payload) => api.post('/simulations/deposit', payload),
  capacity: () => api.get('/simulations/capacity'),
};

export const reportsApi = {
  /** Period keywords the backend accepts: hari_ini, minggu_ini, bulan_ini, … */
  spending: (period = 'bulan_ini') => api.get(`/reports/spending?period=${period}`),
};

export const transactionsApi = {
  /**
   * Filters are applied by the server, never by narrowing a page here:
   * "transfers this month" computed over the last fifty rows is a
   * different question with a quietly different answer.
   */
  list: ({ limit = 50, period, type, accountId } = {}) => {
    const query = new URLSearchParams({ limit: String(limit) });

    if (period) query.set('period', period);
    if (type) query.set('type', type);
    if (accountId) query.set('account_id', accountId);

    return api.get(`/transactions?${query}`);
  },

  /** Impact only. Writes nothing, so it is safe to call as you type. */
  preview: (draft) => api.post('/transactions/preview', draft),

  /**
   * The header is mandatory, not best-effort: AC04 requires a
   * confirmation sent twice to produce exactly one transaction, and the
   * backend answers 422 without it rather than silently dropping the
   * guarantee.
   */
  create: (draft, operationId) =>
    api.post('/transactions', draft, { headers: { 'Idempotency-Key': operationId } }),
};

/**
 * Stream one chat turn, calling `onEvent` for each NDJSON line.
 *
 * Newline-delimited JSON over a plain POST rather than SSE, because
 * `EventSource` cannot POST and we already read the body as a stream.
 *
 * Errors arrive two ways and both matter: as a status code before the
 * stream opens (rate limited, busy), and as an `error` event inside it
 * once it has. By then the 200 has already been sent, so a client that
 * only checked the status would read a failed turn as a success.
 */
export async function streamChat(body, onEvent, { signal } = {}) {
  let response;

  try {
    response = await fetch(`${BASE}/chat/messages/stream`, {
      method: 'POST',
      signal,
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ body }),
    });
  } catch (error) {
    if (error.name === 'AbortError') {
      throw error;
    }
    throw new ApiError('Tidak ada koneksi ke server.', { status: 0, code: 'offline' });
  }

  if (!response.ok) {
    let payload = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    const { code, message } = extractError(response.status, payload);
    throw new ApiError(message, { status: response.status, code, body: payload });
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  // Read line by line: a chunk can split a JSON object anywhere, so
  // the remainder is carried over rather than parsed half-formed.
  for (;;) {
    const { done, value } = await reader.read();

    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      if (line.trim()) {
        onEvent(JSON.parse(line));
      }
    }
  }

  if (buffer.trim()) {
    onEvent(JSON.parse(buffer));
  }
}

export const chatApi = {
  messages: () => api.get('/chat/messages'),
  send: (body, { signal } = {}) => api.post('/chat/messages', { body }, { signal }),
  stream: streamChat,
  confirmDraft: (id) => api.post(`/chat/drafts/${id}/confirm`),
  cancelDraft: (id) => api.post(`/chat/drafts/${id}/cancel`),
};
