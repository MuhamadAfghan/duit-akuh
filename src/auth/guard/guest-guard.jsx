'use client';

import { useState, useEffect } from 'react';
import { safeReturnUrl } from 'minimal-shared/utils';

import { useRouter, useSearchParams } from 'src/routes/hooks';

import { CONFIG } from 'src/global-config';

import { SplashScreen } from 'src/components/loading-screen';

import { useAuthContext } from '../hooks';

// ----------------------------------------------------------------------

export function GuestGuard({ children }) {
  const router = useRouter();

  const { loading, authenticated } = useAuthContext();

  const [isChecking, setIsChecking] = useState(true);

  const searchParams = useSearchParams();
  const redirectUrl = safeReturnUrl(searchParams.get('returnTo'), CONFIG.auth.redirectPath);

  const checkPermissions = async () => {
    if (loading) {
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
  }, [authenticated, loading]);

  if (isChecking) {
    return <SplashScreen />;
  }

  return <>{children}</>;
}
