'use client';

import { useEffect } from 'react';

// ----------------------------------------------------------------------

/**
 * Registers the service worker (PRD FR16).
 *
 * Only runs in production builds: in dev the worker would cache
 * /_next/static and fight hot reloading.
 *
 * A waiting worker is intentionally left waiting. The PRD forbids an update
 * from forcing a reload while a draft is unsaved, so activation is an
 * explicit call to `activateUpdatedServiceWorker()` made once the app knows
 * nothing is pending.
 */
export function ServiceWorkerRegister() {
  useEffect(() => {
    if (process.env.NODE_ENV !== 'production') {
      return;
    }

    if (!('serviceWorker' in navigator)) {
      return;
    }

    const register = () => {
      navigator.serviceWorker.register('/sw.js').catch((error) => {
        console.error('Service worker registration failed:', error);
      });
    };

    if (document.readyState === 'complete') {
      register();
    } else {
      window.addEventListener('load', register, { once: true });
    }
  }, []);

  return null;
}

// ----------------------------------------------------------------------

/**
 * Activates a downloaded update and reloads once it takes over. Call this
 * only when no unsaved draft would be lost.
 */
export async function activateUpdatedServiceWorker() {
  if (!('serviceWorker' in navigator)) {
    return false;
  }

  const registration = await navigator.serviceWorker.getRegistration();

  if (!registration?.waiting) {
    return false;
  }

  navigator.serviceWorker.addEventListener('controllerchange', () => window.location.reload(), {
    once: true,
  });

  registration.waiting.postMessage({ type: 'SKIP_WAITING' });

  return true;
}
