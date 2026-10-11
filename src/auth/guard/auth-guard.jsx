'use client';

import { useState, useEffect } from 'react';

import { paths } from 'src/routes/paths';
import { useRouter, usePathname } from 'src/routes/hooks';

import { SplashScreen } from 'src/components/loading-screen';

import { useAuthContext } from '../hooks';
import { ConnectionError } from '../components/connection-error';

// ----------------------------------------------------------------------

export function AuthGuard({ children }) {
  const router = useRouter();
  const pathname = usePathname();

  const { authenticated, loading, error, checkUserSession } = useAuthContext();

  const [isChecking, setIsChecking] = useState(true);

  const createRedirectPath = (currentPath) => {
    const queryString = new URLSearchParams({ returnTo: pathname }).toString();
    return `${currentPath}?${queryString}`;
  };

  const checkPermissions = async () => {
    if (loading) {
      return;
    }

    // A failed session check is not an answer. Bouncing to sign-in here
    // would throw away the page the user was on to show them a form
    // that cannot work either.
    if (error) {
      return;
    }

    if (!authenticated) {
      router.replace(createRedirectPath(paths.auth.signIn));
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
