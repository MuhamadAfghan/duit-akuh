'use client';

import { useRef, useState, useCallback } from 'react';

import Box from '@mui/material/Box';
import CircularProgress from '@mui/material/CircularProgress';

import { Iconify } from 'src/components/iconify';

// ----------------------------------------------------------------------

/** How far along the track counts as committed. */
const COMMIT_RATIO = 0.82;

const THUMB = 48;
const TRACK_HEIGHT = 56;
const PADDING = 4;

/**
 * Drag-to-confirm, for the one action that moves money.
 *
 * A button is too easy to hit. Every card in this app ends in a write
 * to a ledger, and the cost of an accidental tap is a wrong balance the
 * person then has to notice and reverse. A deliberate gesture costs a
 * moment and buys intent, and Indonesian wallet apps have already
 * taught everyone what the control means.
 *
 * It is still a real `<button>`. Pressing Enter or Space confirms, so
 * the gesture is an addition rather than a requirement — a swipe-only
 * control cannot be operated by keyboard or by a screen reader, which
 * would make the most important action in the product the only one
 * some people cannot reach.
 */
export function SwipeConfirm({
  label = 'Geser untuk simpan',
  busyLabel = 'Menyimpan…',
  onConfirm,
  disabled = false,
  busy = false,
  sx,
}) {
  const trackRef = useRef(null);
  const startRef = useRef(0);
  const draggedRef = useRef(false);

  const [offset, setOffset] = useState(0);
  const [dragging, setDragging] = useState(false);

  const locked = disabled || busy;

  const travel = useCallback(() => {
    const width = trackRef.current?.clientWidth ?? 0;
    return Math.max(width - THUMB - PADDING * 2, 1);
  }, []);

  const handlePointerDown = useCallback(
    (event) => {
      if (locked) {
        return;
      }
      draggedRef.current = false;
      startRef.current = event.clientX;
      setDragging(true);
      event.currentTarget.setPointerCapture?.(event.pointerId);
    },
    [locked]
  );

  const handlePointerMove = useCallback(
    (event) => {
      if (!dragging || locked) {
        return;
      }

      const next = Math.min(Math.max(event.clientX - startRef.current, 0), travel());

      if (next > 4) {
        draggedRef.current = true;
      }

      setOffset(next);
    },
    [dragging, locked, travel]
  );

  const settle = useCallback(() => {
    if (!dragging) {
      return;
    }

    setDragging(false);

    const committed = offset >= travel() * COMMIT_RATIO;
    setOffset(0);

    if (committed) {
      onConfirm?.();
    }
  }, [dragging, offset, travel, onConfirm]);

  const handleClick = useCallback(() => {
    // A pointer drag ends with a click too. Only let the click through
    // when it was a real press: a released-too-early drag means the
    // person changed their mind.
    if (draggedRef.current) {
      draggedRef.current = false;
      return;
    }

    if (!locked) {
      onConfirm?.();
    }
  }, [locked, onConfirm]);

  const progress = offset / travel();

  return (
    <Box
      ref={trackRef}
      sx={[
        (theme) => ({
          p: `${PADDING}px`,
          width: 1,
          height: TRACK_HEIGHT,
          display: 'flex',
          position: 'relative',
          alignItems: 'center',
          borderRadius: 999,
          overflow: 'hidden',
          bgcolor: theme.vars.palette.primary.lighter,
          ...(locked && { opacity: 0.6 }),
        }),
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    >
      <Box
        aria-hidden
        sx={(theme) => ({
          inset: 0,
          position: 'absolute',
          borderRadius: 999,
          bgcolor: theme.vars.palette.primary.main,
          opacity: progress * 0.22,
          pointerEvents: 'none',
        })}
      />

      <Box
        aria-hidden
        sx={{
          px: 2,
          inset: 0,
          display: 'flex',
          position: 'absolute',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'primary.darker',
          typography: 'subtitle1',
          opacity: 1 - progress,
          pointerEvents: 'none',
        }}
      >
        {busy ? busyLabel : label}
      </Box>

      <Box
        component="button"
        type="button"
        disabled={locked}
        aria-label={`${label}. Tekan Enter kalau lebih gampang.`}
        onClick={handleClick}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={settle}
        onPointerCancel={settle}
        sx={(theme) => ({
          p: 0,
          border: 'none',
          width: THUMB,
          height: THUMB,
          flexShrink: 0,
          display: 'flex',
          cursor: locked ? 'default' : 'grab',
          position: 'relative',
          borderRadius: '50%',
          alignItems: 'center',
          justifyContent: 'center',
          // Without this the browser scrolls the thread instead of
          // letting the thumb move.
          touchAction: 'none',
          color: theme.vars.palette.primary.contrastText,
          bgcolor: theme.vars.palette.primary.main,
          transform: `translateX(${offset}px)`,
          transition: dragging ? 'none' : theme.transitions.create('transform'),
          '@media (prefers-reduced-motion: reduce)': { transition: 'none' },
          '&:active': { cursor: locked ? 'default' : 'grabbing' },
        })}
      >
        {busy ? (
          <CircularProgress size={20} color="inherit" />
        ) : (
          <Iconify icon="eva:arrow-ios-forward-fill" width={24} />
        )}
      </Box>
    </Box>
  );
}
