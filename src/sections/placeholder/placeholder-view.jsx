'use client';

// Required: this view is rendered directly by a server page and passes
// callback `sx` props to MUI's client components. A function cannot cross
// the server/client boundary, so without this directive React throws
// "Functions cannot be passed directly to Client Components".

import { varAlpha } from 'minimal-shared/utils';

import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';

import { Iconify } from 'src/components/iconify';

// ----------------------------------------------------------------------

/**
 * Honest placeholder for a surface that is not built yet.
 *
 * States plainly that there is nothing here, rather than showing mock
 * numbers that could be mistaken for real balances.
 */
export function PlaceholderView({ title, description }) {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', flex: '1 1 auto', minHeight: 0 }}>
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
        <Typography variant="h6" component="h1">
          {title}
        </Typography>
      </Box>

      <Stack
        sx={{
          flex: '1 1 auto',
          minHeight: 0,
          overflowY: 'auto',
          px: 3,
          py: 6,
          gap: 2,
          alignItems: 'center',
          justifyContent: 'center',
          textAlign: 'center',
        }}
      >
        <Box
          sx={(theme) => ({
            width: 72,
            height: 72,
            display: 'grid',
            placeItems: 'center',
            borderRadius: '50%',
            color: theme.vars.palette.text.disabled,
            bgcolor: varAlpha(theme.vars.palette.grey['500Channel'], 0.08),
          })}
        >
          <Iconify icon="solar:box-minimalistic-bold" width={32} />
        </Box>

        <Typography variant="subtitle1">Belum dibuat</Typography>

        <Typography variant="body2" sx={{ maxWidth: 420, color: 'text.secondary' }}>
          {description}
        </Typography>
      </Stack>
    </Box>
  );
}
