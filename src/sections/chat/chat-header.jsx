import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';

import { formatRupiahPlain } from 'src/utils/format-money';

import { CONFIG } from 'src/global-config';

// ----------------------------------------------------------------------

/**
 * Chat header.
 *
 * There is intentionally no conversation picker or back button: the PRD
 * specifies a single persistent thread that continues across sessions and
 * devices, so there is nothing to switch between or navigate back from.
 *
 * The free-to-spend chip is the exception to "the header is chrome".
 * It is the single figure the product exists to produce, and having it
 * in view while you type is what stops the chat being a place you go to
 * ask a question you already had to leave to answer.
 */
export function ChatHeader({ status, freeToSpend }) {
  return (
    <Box
      component="header"
      sx={{
        flexShrink: 0,
        px: 2,
        pt: 'calc(env(safe-area-inset-top) + 12px)',
        pb: 1.5,
        bgcolor: 'background.paper',
      }}
    >
      <Stack direction="row" sx={{ gap: 1.5, alignItems: 'center' }}>
        <Typography
          variant="h6"
          component="h1"
          sx={{ flexGrow: 1, minWidth: 0, letterSpacing: '-0.02em' }}
        >
          {CONFIG.appName}
          <Box component="span" sx={{ color: 'primary.main' }}>
            .
          </Box>
        </Typography>

        {status ? (
          <Typography variant="caption" sx={{ color: 'text.secondary' }}>
            {status}
          </Typography>
        ) : (
          freeToSpend != null && (
            <Stack
              direction="row"
              sx={(theme) => ({
                gap: 1,
                px: 1.75,
                height: 36,
                alignItems: 'center',
                borderRadius: 999,
                color: theme.vars.palette.common.white,
                bgcolor: theme.vars.palette.text.primary,
              })}
            >
              <Box component="span" sx={{ typography: 'caption', opacity: 0.64 }}>
                bebas
              </Box>
              <Box
                component="span"
                sx={{ typography: 'subtitle2', fontVariantNumeric: 'tabular-nums' }}
              >
                {formatRupiahPlain(freeToSpend)}
              </Box>
            </Stack>
          )
        )}
      </Stack>
    </Box>
  );
}
