'use client';

import { useEffect } from 'react';

import { CHAT_DRAFT_KEY } from 'src/lib/session-state';

// ----------------------------------------------------------------------

/**
 * Registers the service worker (PRD FR16).
 *
 * Only runs in production builds: in dev the worker would cache
 * /_next/static and fight hot reloading.
 *
 * A waiting worker used to be left waiting for an explicit call that
 * nothing ever made. The PRD forbids an update from reloading over an
 * unsaved draft, and that was read as "never activate" — so a new
 * worker sat in `waiting` until every tab for the origin closed, which
 * on an installed PWA can be never. The app kept running whatever
 * worker first installed, and no fix to it could ever reach anyone.
 *
 * So the rule is applied rather than avoided: activate as soon as there
 * is no draft to lose, and check again whenever the app is brought back
 * to the foreground.
 */
export function ServiceWorkerRegister() {
  useEffect(() => {
    if (process.env.NODE_ENV !== 'production') {
      return undefined;
    }

    if (!('serviceWorker' in navigator)) {
      return undefined;
    }

    let registration = null;

    const tryActivate = () => {
      if (registration?.waiting) {
        activateUpdatedServiceWorker().catch(() => {});
      }
    };

    const register = async () => {
      try {
        registration = await navigator.serviceWorker.register('/sw.js');
      } catch (error) {
        console.error('Service worker registration failed:', error);
        return;
      }

      // One that finished downloading before this page loaded.
      tryActivate();

      registration.addEventListener('updatefound', () => {
        const incoming = registration.installing;

        incoming?.addEventListener('statechange', () => {
          if (incoming.state === 'installed' && navigator.serviceWorker.controller) {
            tryActivate();
          }
        });
      });
    };

    if (document.readyState === 'complete') {
      register();
    } else {
      window.addEventListener('load', register, { once: true });
    }

    // Coming back to the app is the likeliest moment for the draft to
    // have been sent and for an update to be waiting.
    document.addEventListener('visibilitychange', tryActivate);

    return () => {
      document.removeEventListener('visibilitychange', tryActivate);
    };
  }, []);

  return null;
}

// ----------------------------------------------------------------------

/**
 * True when the composer is holding something the person has not sent.
 *
 * Reloading would take it with them, which is the thing the PRD's rule
 * about updates is actually protecting. Guarded because sessionStorage
 * throws in some private-browsing modes; unreadable counts as unsafe.
 */
function hasUnsavedDraft() {
  try {
    return Boolean(sessionStorage.getItem(CHAT_DRAFT_KEY));
  } catch {
    return true;
  }
}

/**
 * Activates a downloaded update and reloads once it takes over.
 *
 * Refuses while a draft is unsent — the next call, on the next
 * foreground, will find it gone.
 */
export async function activateUpdatedServiceWorker() {
  if (!('serviceWorker' in navigator)) {
    return false;
  }

  const registration = await navigator.serviceWorker.getRegistration();

  if (!registration?.waiting || hasUnsavedDraft()) {
    return false;
  }

  navigator.serviceWorker.addEventListener('controllerchange', () => window.location.reload(), {
    once: true,
  });

  registration.waiting.postMessage({ type: 'SKIP_WAITING' });

  return true;
}
