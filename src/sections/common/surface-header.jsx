import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import IconButton from '@mui/material/IconButton';

import { RouterLink } from 'src/routes/components';

import { Iconify } from 'src/components/iconify';

// ----------------------------------------------------------------------

/**
 * Shared header for every surface that is not the chat.
 *
 * `backHref` is for the screens reached from Ringkasan rather than from
 * the tab bar. A tabbed surface must not have a back arrow — there is
 * nowhere behind it — so it is opt-in rather than automatic.
 */
export function SurfaceHeader({ title, action, backHref }) {
  return (
    <Box
      component="header"
      sx={{
        flexShrink: 0,
        px: backHref ? 0.5 : 2,
        pt: 'calc(env(safe-area-inset-top) + 12px)',
        pb: 1.5,
        gap: 1,
        display: 'flex',
        alignItems: 'center',
        bgcolor: 'background.paper',
      }}
    >
      {backHref && (
        <IconButton
          component={RouterLink}
          href={backHref}
          aria-label="Kembali"
          sx={{ width: 44, height: 44, color: 'text.primary' }}
        >
          <Iconify icon="eva:arrow-ios-back-fill" width={22} />
        </IconButton>
      )}

      <Typography
        variant="h6"
        component="h1"
        sx={{ flexGrow: 1, minWidth: 0, letterSpacing: '-0.02em' }}
      >
        {title}
      </Typography>

      {action}
    </Box>
  );
}
