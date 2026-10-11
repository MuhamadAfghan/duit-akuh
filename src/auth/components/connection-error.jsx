'use client';

import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';

import { Iconify } from 'src/components/iconify';

// ----------------------------------------------------------------------

/**
 * Shown by both guards when the session check could not reach the
 * server, instead of a splash screen that never resolves.
 *
 * The browser-extension line is not padding. It is the failure we have
 * actually seen: an extension blocked `fetch('/api/auth/me')` before it
 * left the browser, so a valid session read as signed out and the app
 * sat on the sign-in page saying nothing. Anyone hitting this needs the
 * one hint that distinguishes it from a dead backend.
 */
export function ConnectionError({ error, onRetry, sx }) {
  const offline = error?.isOffline;

  return (
    <Box
      sx={[
        {
          px: 3,
          gap: 2.5,
          minHeight: '100dvh',
          display: 'flex',
          textAlign: 'center',
          alignItems: 'center',
          flexDirection: 'column',
          justifyContent: 'center',
        },
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    >
      <Box
        sx={(theme) => ({
          width: 56,
          height: 56,
          display: 'flex',
          borderRadius: '50%',
          alignItems: 'center',
          justifyContent: 'center',
          color: theme.vars.palette.warning.darker,
          bgcolor: theme.vars.palette.warning.lighter,
        })}
      >
        <Iconify icon="solar:danger-triangle-bold" width={28} />
      </Box>

      <Stack sx={{ gap: 1, maxWidth: 360 }}>
        <Typography variant="h6">Nggak bisa nyambung ke server</Typography>

        <Typography variant="body2" sx={{ color: 'text.secondary' }}>
          {offline
            ? 'Permintaan ke server gagal sebelum sempat terkirim. Biasanya koneksi putus, atau ada ekstensi browser yang memblokir alamatnya.'
            : 'Server menjawab dengan cara yang nggak kebaca. Coba lagi sebentar.'}
        </Typography>

        <Typography variant="caption" sx={{ color: 'text.disabled' }}>
          Kalau diulang masih sama, buka di jendela samaran atau matikan pemblokir iklan buat alamat
          ini.
        </Typography>
      </Stack>

      <Button
        variant="contained"
        onClick={onRetry}
        startIcon={<Iconify icon="solar:restart-bold" />}
      >
        Coba lagi
      </Button>
    </Box>
  );
}
