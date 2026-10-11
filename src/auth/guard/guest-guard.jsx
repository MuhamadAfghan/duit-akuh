'use client';

import { useState, useEffect } from 'react';
import { safeReturnUrl } from 'minimal-shared/utils';

import { useRouter, useSearchParams } from 'src/routes/hooks';

import { CONFIG } from 'src/global-config';

import { SplashScreen } from 'src/components/loading-screen';

import { useAuthContext } from '../hooks';
import { ConnectionError } from '../components/connection-error';

// ----------------------------------------------------------------------

export function GuestGuard({ children }) {
  const router = useRouter();

  const { loading, authenticated, error, checkUserSession } = useAuthContext();

  const [isChecking, setIsChecking] = useState(true);

  const searchParams = useSearchParams();
  const redirectUrl = safeReturnUrl(searchParams.get('returnTo'), CONFIG.auth.redirectPath);

  const checkPermissions = async () => {
    if (loading) {
      return;
    }

    // The session could not be read, so we do not know whether this
    // person is signed in. Showing the form would be a lie: submitting
    // it reaches the same server that just refused to answer.
    if (error) {
      return;
    }

    if (authenticated) {
      router.replace(redirectUrl);
      return;
    }

    setIsChecking(false);
  };

  useEffect(() => {
    checkPermissions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authenticated, loading, error]);

  if (error) {
    return <ConnectionError error={error} onRetry={checkUserSession} />;
  }

  if (isChecking) {
    return <SplashScreen />;
  }

  return <>{children}</>;
}
