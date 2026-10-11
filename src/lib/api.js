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

/**
 * True when the host's protection answered instead of our API.
 *
 * Imunify360 sits in front of this account (`server: openresty`) and
 * answers requests it finds suspicious with a JavaScript challenge
 * page — **status 200**, `content-type: text/html`, "One moment,
 * please...". Our own XHR gets it too, intermittently and more often
 * on mobile.
 *
 * Reported as "Balasan server kosong", which is how it stayed
 * unexplained for a while: the response is not empty, it is 12KB of
 * HTML that is not JSON. Calling it by its name is most of the fix,
 * because the rest of the fix is a hosting setting and nobody looks
 * there while the app is blaming itself.
 */
function isEdgeChallenge(response, text) {
  const type = response.headers.get('content-type') ?? '';

  return type.includes('text/html') && /<title[^>]*>\s*One moment/i.test(text);
}

async function request(path, { method = 'GET', body, headers = {}, signal, retried } = {}) {
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
        // Says plainly that this is an API call and not a page load.
        // It does not stop the WAF on its own, but it is what a filter
        // rule can be written against, and it keeps the backend from
        // redirecting us to the sign-in page the way it now does for a
        // browser navigation.
        Accept: 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
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

  // Returning `null` for any of this was the bug behind "This page
  // couldn't load": `setAccounts(null)` followed by `accounts.map(...)`
  // inside a useMemo throws during render, React unwinds the whole
  // tree, and the browser shows its own error page. Callers already
  // handle a failed request; none can do anything with a silent null.
  //
  // 204 has returned above, so a deliberate no-content reply is fine.
  if (payload === null) {
    if (isEdgeChallenge(response, text)) {
      // The challenge usually passes on a second attempt, so one retry
      // turns most of these into nothing the person ever sees. GET
      // only: replaying a write that may already have landed is
      // exactly what the idempotency rules exist to prevent, and a
      // challenge gives no way to know which side of it we are on.
      if (method === 'GET' && !retried) {
        await new Promise((resolve) => setTimeout(resolve, 400));

        return request(path, { method, body, headers, signal, retried: true });
      }

      throw new ApiError(
        'Permintaan ditahan sama proteksi hosting, bukan sama aplikasinya. Coba lagi sebentar.',
        { status: response.status, code: 'blocked_by_edge' }
      );
    }

    throw new ApiError(
      text
        ? 'Balasan server nggak bisa dibaca. Coba lagi.'
        : 'Server nggak balas apa-apa. Coba lagi.',
      { status: response.status, code: text ? 'bad_response' : 'empty_response' }
    );
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

  /**
   * Succeeds with 204 and no body. The backend revokes every session
   * including this one, so the caller is signed out by the time this
   * resolves and has to send the user back to sign-in.
   */
  changePassword: (currentPassword, newPassword) =>
    api.post('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    }),

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

  /**
   * Earmarks money that stays where it is. `amount` **replaces** this
   * goal's mark on that account rather than adding to it, so sending
   * the same request twice leaves the same figure.
   *
   * The server refuses to earmark more than an account actually holds
   * (AC05), so the error from here is the rule talking, not a
   * validation nicety.
   */
  allocate: (id, accountId, amount) =>
    api.post(`/goals/${id}/allocations`, { account_id: accountId, amount }),

  /** Drops the mark entirely. Zero is not a valid `allocate` amount. */
  release: (id, accountId) => api.post(`/goals/${id}/allocations/release?account_id=${accountId}`),
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
export async function streamChat(
  body,
  onEvent,
  { signal, replyToId = null, conversationId = null } = {}
) {
  let response;

  try {
    response = await fetch(`${BASE}/chat/messages/stream`, {
      method: 'POST',
      signal,
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        body,
        reply_to_id: replyToId,
        conversation_id: conversationId,
      }),
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

  // A 200 that is not our stream: the host's protection answering
  // instead of the app. Without this the reader would hand JSON.parse a
  // line of HTML and the turn would die on a syntax error.
  if (!(response.headers.get('content-type') ?? '').includes('json')) {
    const preview = await response.text();

    if (isEdgeChallenge(response, preview)) {
      throw new ApiError(
        'Permintaan ditahan sama proteksi hosting, bukan sama aplikasinya. Coba lagi sebentar.',
        { status: response.status, code: 'blocked_by_edge' }
      );
    }
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

/**
 * Named threads.
 *
 * `active` is what the chat opens on: it resolves the most recently
 * used thread and creates one when the account has none, so nothing in
 * the UI has to handle "no conversation yet".
 */
export const conversationsApi = {
  list: ({ includeArchived = false } = {}) =>
    api.get(`/chat/conversations${includeArchived ? '?include_archived=true' : ''}`),
  active: () => api.get('/chat/conversations/active'),
  create: () => api.post('/chat/conversations'),
  update: (id, patch) => api.patch(`/chat/conversations/${id}`, patch),
};

export const chatApi = {
  messages: (conversationId = null) =>
    api.get(conversationId ? `/chat/messages?conversation_id=${conversationId}` : '/chat/messages'),
  send: (body, { signal, replyToId = null, conversationId = null } = {}) =>
    api.post(
      '/chat/messages',
      { body, reply_to_id: replyToId, conversation_id: conversationId },
      { signal }
    ),
  stream: streamChat,
  confirmDraft: (id) => api.post(`/chat/drafts/${id}/confirm`),
  /**
   * Edits a pending draft. Returns a *different* draft: the server
   * cancels this one and replaces it, so the id you had stops working.
   */
  reviseDraft: (id, patch) => api.post(`/chat/drafts/${id}/revise`, { patch }),
  cancelDraft: (id) => api.post(`/chat/drafts/${id}/cancel`),
};
