import Box from '@mui/material/Box';

import { APP_COLUMN_WIDTH } from 'src/layouts/app/column';

import { GuestGuard } from 'src/auth/guard';

// ----------------------------------------------------------------------

/**
 * Chrome and the guard for every auth screen.
 *
 * The guard used to be copied into each page's own layout, which is how
 * five screens would have become five copies of the same wrapper — and
 * how a sixth could quietly ship with no guard at all.
 *
 * The template's split layout is gone. Phone is the primary device, so
 * the first screen somebody sees is the same single column as the rest
 * of the app rather than a desktop brochure that folds awkwardly. On a
 * wide window the column simply centres.
 */
export default function Layout({ children }) {
  return (
    <GuestGuard>
      <Box
        sx={{
          minHeight: '100dvh',
          display: 'flex',
          justifyContent: 'center',
          bgcolor: 'background.paper',
        }}
      >
        <Box
          sx={{
            px: 3,
            pt: 'calc(env(safe-area-inset-top) + 44px)',
            width: 1,
            maxWidth: APP_COLUMN_WIDTH,
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {children}
        </Box>
      </Box>
    </GuestGuard>
  );
}
