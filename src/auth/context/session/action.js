'use client';

import { authApi } from 'src/lib/api';

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

export async function signOut() {
  await authApi.logout();
}
