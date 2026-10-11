import { varAlpha } from 'minimal-shared/utils';

import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';

import { AssistantMark } from './chat-message';

// ----------------------------------------------------------------------

/** Staggered so the three dots read as one wave rather than a blink. */
const DELAYS = ['0s', '0.16s', '0.32s'];

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
                opacity: 0.4,
                borderRadius: '50%',
                animationDelay: delay,
                bgcolor: theme.vars.palette.primary.main,
                animation: 'lega-typing 1.25s ease-in-out infinite',
                '@keyframes lega-typing': {
                  '0%, 72%, 100%': { transform: 'translateY(0)', opacity: 0.4 },
                  '36%': { transform: 'translateY(-5px)', opacity: 1 },
                },
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
