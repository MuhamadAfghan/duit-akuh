import { varAlpha } from 'minimal-shared/utils';

import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';

import { Iconify } from 'src/components/iconify';

// ----------------------------------------------------------------------

/** Empty or error state. States plainly that there is nothing, never fake data. */
export function SurfaceEmpty({ icon = 'solar:box-minimalistic-bold', title, body }) {
  return (
    <Stack
      sx={{
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
        <Iconify icon={icon} width={32} />
      </Box>

      <Typography variant="subtitle1">{title}</Typography>

      <Typography variant="body2" sx={{ maxWidth: 420, color: 'text.secondary' }}>
        {body}
      </Typography>
    </Stack>
  );
}
