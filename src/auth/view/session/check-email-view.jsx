'use client';

import { useState, useEffect } from 'react';
import { useCountdownSeconds } from 'minimal-shared/hooks';

import Box from '@mui/material/Box';
import Link from '@mui/material/Link';
import Stack from '@mui/material/Stack';
import Button from '@mui/material/Button';

import { paths } from 'src/routes/paths';
import { RouterLink } from 'src/routes/components';

import { authApi } from 'src/lib/api';

import { Iconify } from 'src/components/iconify';

import { getErrorMessage } from '../../utils';
import { RESET_EMAIL_KEY } from './forgot-password-view';
import { AuthHead, AuthNote, AuthFooter, AuthSubmit } from '../../components/auth-kit';

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
      <Box sx={{ flexGrow: 1 }}>
        <AuthHead
          icon={
            <Box
              sx={{
                width: 72,
                height: 72,
                display: 'grid',
                borderRadius: 2.5,
                placeItems: 'center',
                color: 'primary.darker',
                bgcolor: 'primary.lighter',
              }}
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
          <Box sx={{ mt: 2.5 }}>
            <AuthNote tone="bad" icon="solar:danger-triangle-bold">
              {errorMessage}
            </AuthNote>
          </Box>
        )}

        {resent && !errorMessage && (
          <Box sx={{ mt: 2.5 }}>
            <AuthNote tone="good" icon="solar:check-circle-bold">
              Tautan baru dikirim. Yang lama otomatis nggak berlaku lagi.
            </AuthNote>
          </Box>
        )}

        <Box sx={{ mt: 3 }}>
          {countdown.isCounting || !email ? (
            <Button
              fullWidth
              disabled
              startIcon={<Iconify icon="lega:clock" width={19} />}
              sx={{
                height: 56,
                fontSize: 15,
                fontWeight: 800,
                borderRadius: 999,
                bgcolor: 'grey.100',
                '&.Mui-disabled': { color: 'text.disabled', bgcolor: 'grey.100' },
              }}
            >
              {email ? `Kirim ulang dalam ${countdown.value}s` : 'Kirim ulang'}
            </Button>
          ) : (
            <AuthSubmit type="button" onClick={onResend}>
              Kirim ulang
            </AuthSubmit>
          )}
        </Box>

        {!email && (
          <Box sx={{ mt: 2, textAlign: 'center' }}>
            <Link
              component={RouterLink}
              href={paths.auth.forgot}
              sx={{ fontSize: 14, fontWeight: 800, color: 'primary.dark' }}
            >
              Masukin emailnya lagi
            </Link>
          </Box>
        )}

        <Stack sx={{ mt: 3, gap: 1.5 }}>
          <AuthNote title="Kenapa kalimatnya “kalau terdaftar”">
            Kalau halaman ini bilang “email nggak ketemu”, siapa pun bisa pakai dia buat ngecek
            alamat mana yang punya akun di sini. Jadi jawabannya sengaja sama buat semua alamat.
          </AuthNote>

          <AuthNote tone="warn" title="Nggak nyampe juga?">
            Cek folder spam dulu. Kalau tetap kosong, kemungkinan akunnya kedaftar pakai alamat
            lain.
          </AuthNote>
        </Stack>
      </Box>

      <AuthFooter label="Kembali ke halaman masuk" href={paths.auth.signIn} />
    </>
  );
}
