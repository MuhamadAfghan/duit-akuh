'use client';

import { authApi } from 'src/lib/api';
import { clearSessionState } from 'src/lib/session-state';

// ----------------------------------------------------------------------

/**
 * Sign-in, sign-up and sign-out against our backend.
 *
 * None of these return or store a token: the backend sets an httpOnly
 * session cookie, and the browser carries it. Callers refresh the auth
 * context with `checkUserSession()` afterwards.
 */

export async function signInWithPassword({ email, password }) {
  return authApi.login(email, password);
}

export async function signUp({ email, password }) {
  return authApi.register(email, password);
}

/**
 * The cookie is the server's to revoke, but anything this tab wrote is
 * ours to clean up — sessionStorage does not end with the account, and
 * the next person to sign in on this phone should not inherit a draft.
 * Cleared only once the server has actually ended the session: a failed
 * logout leaves the user signed in, and throwing their unsent text away
 * would be a second loss on top of the first.
 */
export async function signOut() {
  await authApi.logout();
  clearSessionState();
}
