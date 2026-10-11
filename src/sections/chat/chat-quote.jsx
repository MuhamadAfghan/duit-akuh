import { varAlpha } from 'minimal-shared/utils';

import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';

import { CONFIG } from 'src/global-config';

// ----------------------------------------------------------------------

/**
 * The block above a reply, and the strip above the composer.
 *
 * One component for both because they are the same claim — *this is
 * what I am answering* — and letting them drift would mean the thing
 * you picked and the thing that got sent could look like two different
 * messages.
 *
 * `onDark` is the version that sits inside the person's own ink bubble.
 * The accent bar stays for both: a quote is the one place a left border
 * means something rather than decorating a card, and it is the
 * convention every chat app has trained people on.
 */
export function ChatQuote({ role, excerpt, onDark = false, sx }) {
  const who = role === 'assistant' ? CONFIG.appName : 'Kamu';

  return (
    <Box
      sx={[
        (theme) => ({
          px: 1.25,
          py: 0.875,
          display: 'flex',
          minWidth: 0,
          borderLeft: '2px solid',
          borderRadius: '4px 11px 11px 4px',
          borderColor: onDark ? theme.vars.palette.primary.light : theme.vars.palette.primary.main,
          bgcolor: onDark
            ? varAlpha(theme.vars.palette.common.whiteChannel, 0.11)
            : theme.vars.palette.grey[100],
        }),
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    >
      <Box sx={{ minWidth: 0 }}>
        <Typography
          sx={(theme) => ({
            fontSize: 10,
            fontWeight: 800,
            letterSpacing: '0.04em',
            textTransform: 'uppercase',
            color: onDark ? theme.vars.palette.primary.light : theme.vars.palette.primary.dark,
          })}
        >
          {who}
        </Typography>

        {/* One line, clipped. A quote that grows with the message it
            points at would push the reply itself off the screen. */}
        <Typography
          noWrap
          sx={(theme) => ({
            mt: 0.125,
            fontSize: 12,
            fontWeight: 600,
            color: onDark
              ? varAlpha(theme.vars.palette.common.whiteChannel, 0.78)
              : theme.vars.palette.text.secondary,
          })}
        >
          {excerpt}
        </Typography>
      </Box>
    </Box>
  );
}
