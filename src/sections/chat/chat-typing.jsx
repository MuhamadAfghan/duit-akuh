import { varAlpha } from 'minimal-shared/utils';

import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';

import { AssistantMark } from './chat-message';

// ----------------------------------------------------------------------

/**
 * One dot at a time.
 *
 * The cycle is 1.2s and each dot waits exactly a third of it, so the
 * second starts only once the first has landed: left, middle, right,
 * pause, again. An earlier version overlapped them — a 0.15s stagger
 * against a 0.6s bounce — and three dots in the air together read as
 * one blinking row rather than as a sequence.
 */
const CYCLE = 1.2;
const DELAYS = ['0s', `${CYCLE / 3}s`, `${(CYCLE * 2) / 3}s`];

/**
 * The bounce, finished inside the first third of the cycle.
 *
 * It was one linear-ish hop on a single ease-in-out, which is why it
 * read as mechanical: a dot that rises and falls at the same rate is a
 * lift, not a bounce. Real weight needs three different rates, so the
 * easing is declared per segment rather than once for the whole
 * animation — up fast and decelerating, down accelerating under
 * gravity, then a short springy settle through a squash.
 *
 * The travel and the scale do the rest of the work. Five pixels on an
 * 8px dot is barely a nudge on a phone held at arm's length; nine plus
 * a little swell is a movement you can see without looking for it.
 *
 * Everything after 33% is deliberately still. That stillness is what
 * hands the movement to the next dot and, once all three have gone,
 * separates one pass from the next.
 */
const BOUNCE = {
  '0%': {
    opacity: 0.3,
    transform: 'translateY(0) scale(1)',
    animationTimingFunction: 'cubic-bezier(0.22, 0.9, 0.3, 1)',
  },
  '13%': {
    opacity: 1,
    transform: 'translateY(-9px) scale(1.16)',
    animationTimingFunction: 'cubic-bezier(0.55, 0, 0.75, 0.4)',
  },
  '26%': {
    opacity: 0.8,
    transform: 'translateY(0) scale(0.86)',
    animationTimingFunction: 'cubic-bezier(0.3, 1.5, 0.5, 1)',
  },
  '33%, 100%': {
    opacity: 0.3,
    transform: 'translateY(0) scale(1)',
  },
};

/**
 * What the thread shows between sending and the first token.
 *
 * Two layers, because the wait has two different lengths. The dots say
 * "something is happening" and cover the ordinary second or two. The
 * line underneath says *what* is happening, and earns its place when the
 * assistant is running tools: `lumi-ai` is a dev box with no SLA and
 * Cloudflare gives up at 100s, so a long pause is a real possibility and
 * a silent one is indistinguishable from a hang.
 *
 * `stage` is the caller's sentence, already chosen from the tool name.
 * When there is none the dots stand alone rather than inventing a label.
 *
 * `role="status"` with `aria-live="polite"` so a screen reader is told
 * once, without interrupting whatever it is reading.
 */
export function ChatTyping({ stage }) {
  return (
    <Box sx={{ gap: 1, display: 'flex', flexDirection: 'column' }}>
      <Box sx={{ gap: 1, display: 'flex', alignItems: 'flex-end' }}>
        <AssistantMark />

        <Box
          role="status"
          aria-live="polite"
          aria-label="lega sedang menulis jawaban"
          sx={(theme) => ({
            px: 2.125,
            gap: 0.75,
            height: 42,
            display: 'flex',
            alignItems: 'center',
            bgcolor: theme.vars.palette.background.paper,
            borderRadius: '18px 18px 18px 6px',
            boxShadow: `0 1px 2px ${varAlpha(theme.vars.palette.grey['800Channel'], 0.07)}`,
          })}
        >
          {DELAYS.map((delay) => (
            <Box
              key={delay}
              aria-hidden
              sx={(theme) => ({
                width: 8,
                height: 8,
                opacity: 0.3,
                borderRadius: '50%',
                bgcolor: theme.vars.palette.primary.main,
                // The delay belongs *inside* the shorthand. It used to
                // sit above it as its own `animationDelay`, where the
                // shorthand then reset it to 0 — which is why all three
                // dots bounced in unison for as long as this existed.
                animation: `lega-typing ${CYCLE}s linear ${delay} infinite`,
                // Each dot gets its own compositor layer; without it the
                // three repaint together and the wave judders on a
                // mid-range phone.
                willChange: 'transform, opacity',
                '@keyframes lega-typing': BOUNCE,
                // FR18 asks for reduced motion to be respected. The dots
                // still have to read as "waiting", so they stay visible
                // at full strength rather than disappearing.
                '@media (prefers-reduced-motion: reduce)': {
                  opacity: 0.75,
                  animation: 'none',
                },
              })}
            />
          ))}
        </Box>
      </Box>

      {stage && (
        <Box sx={{ gap: 0.75, pl: 4.25, display: 'flex', alignItems: 'center' }}>
          <Box
            aria-hidden
            sx={(theme) => ({
              width: 13,
              height: 13,
              flexShrink: 0,
              borderRadius: '50%',
              border: `2.5px solid ${theme.vars.palette.grey[300]}`,
              borderTopColor: theme.vars.palette.primary.main,
              animation: 'lega-spin 0.95s linear infinite',
              '@keyframes lega-spin': { to: { transform: 'rotate(360deg)' } },
              '@media (prefers-reduced-motion: reduce)': { animation: 'none' },
            })}
          />

          <Typography sx={{ fontSize: 12, fontWeight: 700, color: 'text.secondary' }}>
            {stage}
          </Typography>
        </Box>
      )}
    </Box>
  );
}
