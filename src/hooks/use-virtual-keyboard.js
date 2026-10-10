'use client';

import { useState, useEffect } from 'react';

// ----------------------------------------------------------------------

/**
 * Tracks how much of the layout viewport the on-screen keyboard covers.
 *
 * Needed because `100dvh` alone does not shrink for the keyboard on iOS
 * Safari, which would leave the chat composer hidden behind it. The
 * visualViewport API reports the actually-visible region, so the shell can
 * compress by exactly that amount (PRD FR17: "composer tetap terlihat di
 * atas keyboard tanpa menutupi pesan/konfirmasi").
 *
 * @returns {{ keyboardInset: number, isKeyboardOpen: boolean }}
 */
export function useVirtualKeyboard() {
  const [keyboardInset, setKeyboardInset] = useState(0);

  useEffect(() => {
    const viewport = window.visualViewport;

    if (!viewport) {
      return undefined;
    }

    const measure = () => {
      // Portion of the layout viewport hidden below the visible area.
      const hidden = window.innerHeight - viewport.height - viewport.offsetTop;
      setKeyboardInset(Math.max(0, Math.round(hidden)));
    };

    measure();

    viewport.addEventListener('resize', measure);
    viewport.addEventListener('scroll', measure);

    return () => {
      viewport.removeEventListener('resize', measure);
      viewport.removeEventListener('scroll', measure);
    };
  }, []);

  return {
    keyboardInset,
    /**
     * Threshold, not `> 0`: browser chrome collapsing on scroll also shrinks
     * the visual viewport by a few dozen pixels, which must not be mistaken
     * for a keyboard and hide the tab bar.
     */
    isKeyboardOpen: keyboardInset > 120,
  };
}
