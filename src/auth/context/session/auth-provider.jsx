'use client';

import { useMemo, useState, useEffect, useCallback } from 'react';

import { authApi, ApiError } from 'src/lib/api';

import { AuthContext } from '../auth-context';

// ----------------------------------------------------------------------

/**
 * Session-cookie auth against our own backend.
 *
 * Replaces the template's JWT provider, which kept an access token in
 * sessionStorage and attached it as a Bearer header. Our session is an
 * httpOnly cookie: JavaScript cannot read it, so there is nothing here
 * to store, refresh, or leak. "Am I signed in?" is answered by asking
 * the server, not by inspecting a token.
 *
 * The state carries three outcomes, not two. "Signed out" and "could
 * not reach the server" look identical to a guard that only tracks a
 * user, and collapsing them is what made a browser extension blocking
 * `/auth/me` look like a sign-in page that ignores you: the request
 * never left the browser, the session was perfectly valid, and the app
 * had no way to say so.
 */
export function AuthProvider({ children }) {
  const [state, setState] = useState({ user: null, loading: true, error: null });

  const checkUserSession = useCallback(async () => {
    try {
      const user = await authApi.me();
      setState({ user, loading: false, error: null });
    } catch (error) {
      if (error instanceof ApiError && error.isUnauthorized) {
        // Not signed in. An ordinary state, not a failure.
        setState({ user: null, loading: false, error: null });
        return;
      }

      // Offline, the backend is down, or something in the browser
      // refused to make the request. Unauthenticated as far as the UI
      // is concerned, but the user needs to be told which it was.
      console.error('Gagal memeriksa sesi:', error);
      setState({ user: null, loading: false, error });
    }
  }, []);

  useEffect(() => {
    checkUserSession();
  }, [checkUserSession]);

  const value = useMemo(
    () => ({
      user: state.user,
      loading: state.loading,
      error: state.error,
      authenticated: Boolean(state.user),
      unauthenticated: !state.loading && !state.user,
      checkUserSession,
    }),
    [state, checkUserSession]
  );

  return <AuthContext value={value}>{children}</AuthContext>;
}
