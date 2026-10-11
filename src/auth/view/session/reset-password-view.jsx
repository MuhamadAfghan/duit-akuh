'use client';

import * as z from 'zod';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useBoolean } from 'minimal-shared/hooks';
import { zodResolver } from '@hookform/resolvers/zod';

import Box from '@mui/material/Box';
import Link from '@mui/material/Link';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import InputAdornment from '@mui/material/InputAdornment';

import { paths } from 'src/routes/paths';
import { useSearchParams } from 'src/routes/hooks';
import { RouterLink } from 'src/routes/components';

import { authApi } from 'src/lib/api';

import { Iconify } from 'src/components/iconify';
import { Form, Field } from 'src/components/hook-form';

import { getErrorMessage } from '../../utils';
import { FormHead } from '../../components/form-head';
import { FormReturnLink } from '../../components/form-return-link';

// ----------------------------------------------------------------------

export const ResetPasswordSchema = z.object({
  password: z
    .string()
    .min(1, { message: 'Kata sandi wajib diisi' })
    // The backend's MIN_PASSWORD_LENGTH. Keep the two in step or the
    // server does the rejecting after a round trip.
    .min(8, { message: 'Kata sandi minimal 8 karakter' }),
});

// ----------------------------------------------------------------------

export function ResetPasswordView() {
  const searchParams = useSearchParams();
  const token = searchParams.get('token');

  const showPassword = useBoolean();

  const [errorMessage, setErrorMessage] = useState(null);
  const [done, setDone] = useState(false);

  const methods = useForm({
    resolver: zodResolver(ResetPasswordSchema),
    defaultValues: { password: '' },
  });

  const {
    watch,
    handleSubmit,
    formState: { isSubmitting },
  } = methods;

  const password = watch('password');

  const onSubmit = handleSubmit(async (data) => {
    setErrorMessage(null);

    try {
      await authApi.resetPassword(token, data.password);
      setDone(true);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    }
  });

  if (!token) {
    return (
      <>
        <FormHead
          title="Tautannya nggak lengkap"
          description="Alamat ini kehilangan bagian token-nya. Biasanya kepotong waktu disalin dari email."
        />

        <Button
          fullWidth
          size="large"
          color="inherit"
          variant="contained"
          component={RouterLink}
          href={paths.auth.forgot}
        >
          Minta tautan baru
        </Button>

        <FormReturnLink href={paths.auth.signIn} label="Kembali ke halaman masuk" />
      </>
    );
  }

  if (done) {
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
                color: theme.vars.palette.primary.contrastText,
                bgcolor: theme.vars.palette.primary.main,
              })}
            >
              <Iconify icon="solar:check-circle-bold" width={38} />
            </Box>
          }
          title="Kata sandi diganti"
          description="Semua sesi lama sudah dikeluarkan. Masuk lagi pakai yang baru."
        />

        <Box
          sx={{
            mb: 3,
            p: 2,
            gap: 1,
            display: 'flex',
            borderRadius: 2,
            flexDirection: 'column',
            bgcolor: 'background.neutral',
            typography: 'caption',
            color: 'text.secondary',
          }}
        >
          <span>Tautan resetnya sudah hangus.</span>
          <span>Catatan dan kantong lu nggak ada yang berubah.</span>
        </Box>

        <Button
          fullWidth
          size="large"
          color="inherit"
          variant="contained"
          component={RouterLink}
          href={paths.auth.signIn}
        >
          Masuk
        </Button>
      </>
    );
  }

  return (
    <>
      <FormHead
        title="Kata sandi baru"
        description="Pakai tombol mata buat ngecek — nggak perlu ngetik dua kali."
        sx={{ textAlign: { xs: 'center', md: 'left' } }}
      />

      {!!errorMessage && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {errorMessage}{' '}
          <Link component={RouterLink} href={paths.auth.forgot} color="inherit">
            Minta tautan baru
          </Link>
        </Alert>
      )}

      <Form methods={methods} onSubmit={onSubmit}>
        <Box sx={{ gap: 3, display: 'flex', flexDirection: 'column' }}>
          <Field.Text
            name="password"
            label="Kata sandi baru"
            type={showPassword.value ? 'text' : 'password'}
            slotProps={{
              inputLabel: { shrink: true },
              input: {
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton
                      onClick={showPassword.onToggle}
                      edge="end"
                      aria-label={
                        showPassword.value ? 'Sembunyikan kata sandi' : 'Tampilkan kata sandi'
                      }
                    >
                      <Iconify
                        icon={showPassword.value ? 'solar:eye-bold' : 'solar:eye-closed-bold'}
                      />
                    </IconButton>
                  </InputAdornment>
                ),
              },
            }}
          />

          <Box sx={{ gap: 1, display: 'flex', flexDirection: 'column' }}>
            <Rule met={password.length >= 8} label="Minimal 8 karakter" />
            <Rule met={/\d/.test(password)} label="Ada angkanya" />
          </Box>

          <Box
            sx={{
              p: 2,
              gap: 0.5,
              display: 'flex',
              borderRadius: 2,
              flexDirection: 'column',
              bgcolor: 'warning.lighter',
              color: 'warning.darker',
            }}
          >
            <Box sx={{ typography: 'subtitle2' }}>Semua perangkat bakal keluar</Box>
            <Box sx={{ typography: 'caption' }}>
              Termasuk HP lain yang masih kebuka. Itu memang gunanya: kalau ada yang nebeng di akun
              lu, dia ikut keluar.
            </Box>
          </Box>

          <Button
            fullWidth
            color="inherit"
            size="large"
            type="submit"
            variant="contained"
            loading={isSubmitting}
            loadingIndicator="Menyimpan…"
          >
            Simpan kata sandi
          </Button>
        </Box>
      </Form>

      <FormReturnLink href={paths.auth.signIn} label="Kembali ke halaman masuk" />
    </>
  );
}

// ----------------------------------------------------------------------

function Rule({ met, label }) {
  return (
    <Box sx={{ gap: 1, display: 'flex', alignItems: 'center' }}>
      <Box
        sx={(theme) => ({
          width: 18,
          height: 18,
          display: 'flex',
          flexShrink: 0,
          borderRadius: '50%',
          alignItems: 'center',
          justifyContent: 'center',
          color: met ? theme.vars.palette.primary.contrastText : 'transparent',
          bgcolor: met ? theme.vars.palette.primary.main : 'transparent',
          border: met ? 'none' : `2px solid ${theme.vars.palette.divider}`,
        })}
      >
        <Iconify icon="eva:checkmark-fill" width={12} />
      </Box>

      <Box sx={{ typography: 'caption', color: met ? 'text.primary' : 'text.secondary' }}>
        {label}
      </Box>
    </Box>
  );
}
