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
 */
export function AuthProvider({ children }) {
  const [state, setState] = useState({ user: null, loading: true });

  const checkUserSession = useCallback(async () => {
    try {
      const user = await authApi.me();
      setState({ user, loading: false });
    } catch (error) {
      if (error instanceof ApiError && error.isUnauthorized) {
        // Not signed in. An ordinary state, not a failure.
        setState({ user: null, loading: false });
        return;
      }

      // Offline or the backend is down. Also unauthenticated as far as
      // the UI is concerned, but worth surfacing rather than swallowing.
      console.error('Gagal memeriksa sesi:', error);
      setState({ user: null, loading: false });
    }
  }, []);

  useEffect(() => {
    checkUserSession();
  }, [checkUserSession]);

  const value = useMemo(
    () => ({
      user: state.user,
      loading: state.loading,
      authenticated: Boolean(state.user),
      unauthenticated: !state.loading && !state.user,
      checkUserSession,
    }),
    [state, checkUserSession]
  );

  return <AuthContext value={value}>{children}</AuthContext>;
}
