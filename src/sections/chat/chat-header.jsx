import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';

import { CONFIG } from 'src/global-config';

// ----------------------------------------------------------------------

/**
 * Chat header.
 *
 * There is intentionally no conversation picker or back button: the PRD
 * specifies a single persistent thread that continues across sessions and
 * devices, so there is nothing to switch between or navigate back from.
 */
export function ChatHeader({ status }) {
  return (
    <Box
      component="header"
      sx={(theme) => ({
        flexShrink: 0,
        px: 2,
        pt: 'calc(env(safe-area-inset-top) + 12px)',
        pb: 1.5,
        bgcolor: theme.vars.palette.background.paper,
        borderBottom: `solid 1px ${theme.vars.palette.divider}`,
      })}
    >
      <Stack direction="row" sx={{ alignItems: 'center', justifyContent: 'space-between' }}>
        <Typography variant="h6" component="h1">
          {CONFIG.appName}
        </Typography>

        {status && (
          <Typography variant="caption" sx={{ color: 'text.secondary' }}>
            {status}
          </Typography>
        )}
      </Stack>
    </Box>
  );
}
