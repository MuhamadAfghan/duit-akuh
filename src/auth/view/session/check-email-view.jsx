'use client';

import { useState, useEffect } from 'react';
import { useCountdownSeconds } from 'minimal-shared/hooks';

import Box from '@mui/material/Box';
import Link from '@mui/material/Link';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';

import { paths } from 'src/routes/paths';

import { authApi } from 'src/lib/api';

import { Iconify } from 'src/components/iconify';

import { getErrorMessage } from '../../utils';
import { FormHead } from '../../components/form-head';
import { RESET_EMAIL_KEY } from './forgot-password-view';
import { FormReturnLink } from '../../components/form-return-link';

// ----------------------------------------------------------------------

const RESEND_SECONDS = 60;

export function CheckEmailView() {
  const [email, setEmail] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);
  const [resent, setResent] = useState(false);

  const countdown = useCountdownSeconds(RESEND_SECONDS);
  const { start } = countdown;

  useEffect(() => {
    try {
      setEmail(sessionStorage.getItem(RESET_EMAIL_KEY));
    } catch {
      // Private mode. The copy below reads fine without the address.
    }

    start();
  }, [start]);

  const onResend = async () => {
    if (!email) {
      return;
    }

    setErrorMessage(null);

    try {
      await authApi.forgotPassword(email);
      setResent(true);
      countdown.reset();
      countdown.start();
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    }
  };

  return (
    <>
      <FormHead
        icon={
          <Box
            sx={(theme) => ({
              width: 72,
              height: 72,
              display: 'flex',
              borderRadius: 2.5,
              alignItems: 'center',
              justifyContent: 'center',
              color: theme.vars.palette.primary.darker,
              bgcolor: theme.vars.palette.primary.lighter,
            })}
          >
            <Iconify icon="solar:letter-bold" width={34} />
          </Box>
        }
        title="Cek email lu"
        description={
          email
            ? `Kalau ${email} terdaftar, tautannya udah nyampe. Berlaku 60 menit.`
            : 'Kalau alamatnya terdaftar, tautannya udah nyampe. Berlaku 60 menit.'
        }
      />

      {!!errorMessage && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {errorMessage}
        </Alert>
      )}

      {resent && !errorMessage && (
        <Alert severity="success" sx={{ mb: 3 }}>
          Tautan baru dikirim. Yang lama otomatis nggak berlaku lagi.
        </Alert>
      )}

      <Button
        fullWidth
        size="large"
        color="inherit"
        variant="contained"
        disabled={countdown.isCounting || !email}
        onClick={onResend}
      >
        {countdown.isCounting ? `Kirim ulang dalam ${countdown.value}s` : 'Kirim ulang'}
      </Button>

      {!email && (
        <Box sx={{ mt: 2, textAlign: 'center', typography: 'body2' }}>
          <Link href={paths.auth.forgot} variant="subtitle2">
            Masukin emailnya lagi
          </Link>
        </Box>
      )}

      <Box
        sx={{
          mt: 3,
          p: 2,
          gap: 1,
          display: 'flex',
          borderRadius: 2,
          flexDirection: 'column',
          bgcolor: 'background.neutral',
        }}
      >
        <Box sx={{ typography: 'subtitle2' }}>Kenapa kalimatnya “kalau terdaftar”</Box>
        <Box sx={{ typography: 'caption', color: 'text.secondary' }}>
          Kalau halaman ini bilang “email nggak ketemu”, siapa pun bisa pakai dia buat ngecek alamat
          mana yang punya akun di sini. Jadi jawabannya sengaja sama buat semua alamat.
        </Box>
      </Box>

      <Box sx={{ mt: 2, typography: 'caption', color: 'text.secondary', textAlign: 'center' }}>
        Nggak nyampe juga? Cek folder spam dulu. Kalau tetap kosong, kemungkinan akunnya kedaftar
        pakai alamat lain.
      </Box>

      <FormReturnLink href={paths.auth.signIn} label="Kembali ke halaman masuk" />
    </>
  );
}
