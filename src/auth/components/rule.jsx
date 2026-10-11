'use client';

import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';

import { Iconify } from 'src/components/iconify';

// ----------------------------------------------------------------------

/**
 * One password requirement, ticked as it is met.
 *
 * Shown under the field from the first keystroke rather than after a
 * rejection: a rule you only learn by failing is a quiz.
 */
export function Rule({ met, label }) {
  return (
    <Stack direction="row" sx={{ gap: 1.25, alignItems: 'center' }}>
      <Box
        sx={(theme) => ({
          width: 20,
          height: 20,
          flexShrink: 0,
          display: 'grid',
          placeItems: 'center',
          borderRadius: '50%',
          color: met ? theme.vars.palette.primary.contrastText : 'transparent',
          bgcolor: met ? theme.vars.palette.primary.main : 'transparent',
          border: met ? 'none' : `2px solid ${theme.vars.palette.grey[300]}`,
        })}
      >
        <Iconify icon="eva:checkmark-fill" width={12} />
      </Box>

      <Box
        component="span"
        sx={{
          fontSize: 14,
          fontWeight: met ? 700 : 600,
          color: met ? 'text.primary' : 'text.secondary',
        }}
      >
        {label}
      </Box>
    </Stack>
  );
}
