'use client';

import * as z from 'zod';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useBoolean } from 'minimal-shared/hooks';
import { zodResolver } from '@hookform/resolvers/zod';

import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import IconButton from '@mui/material/IconButton';
import InputAdornment from '@mui/material/InputAdornment';

import { paths } from 'src/routes/paths';
import { useSearchParams } from 'src/routes/hooks';

import { authApi } from 'src/lib/api';

import { Form } from 'src/components/hook-form';
import { Iconify } from 'src/components/iconify';

import { Rule } from '../../components/rule';
import { getErrorMessage } from '../../utils';
import { AuthHead, AuthNote, AuthField, AuthFooter, AuthSubmit } from '../../components/auth-kit';

// ----------------------------------------------------------------------

export const ResetPasswordSchema = z.object({
  password: z
    .string()
    .min(1, { message: 'Kata sandi wajib diisi' })
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
        <Box sx={{ flexGrow: 1 }}>
          <AuthHead
            title="Tautannya nggak lengkap"
            description="Alamat ini kehilangan bagian tokennya. Biasanya kepotong waktu disalin dari email."
          />

          <Box sx={{ mt: 3 }}>
            <AuthSubmit href={paths.auth.forgot}>Minta tautan baru</AuthSubmit>
          </Box>
        </Box>

        <AuthFooter label="Kembali ke halaman masuk" href={paths.auth.signIn} />
      </>
    );
  }

  if (done) {
    return (
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
                color: 'primary.contrastText',
                bgcolor: 'primary.main',
              }}
            >
              <Iconify icon="solar:check-circle-bold" width={38} />
            </Box>
          }
          title="Kata sandi diganti"
          description="Semua sesi lama sudah dikeluarkan. Masuk lagi pakai yang baru."
        />

        <Stack sx={{ mt: 3, gap: 1.5 }}>
          <AuthNote icon="solar:check-circle-bold">Tautan resetnya sudah hangus.</AuthNote>
          <AuthNote icon="solar:check-circle-bold">
            Catatan dan kantong lu nggak ada yang berubah.
          </AuthNote>
        </Stack>

        <Box sx={{ mt: 3 }}>
          <AuthSubmit href={paths.auth.signIn}>Masuk</AuthSubmit>
        </Box>
      </Box>
    );
  }

  return (
    <>
      <Box sx={{ flexGrow: 1 }}>
        <AuthHead
          title="Kata sandi baru"
          description="Pakai tombol mata buat ngecek — nggak perlu ngetik dua kali."
        />

        {!!errorMessage && (
          <Box sx={{ mt: 2.5 }}>
            <AuthNote tone="bad" icon="solar:danger-triangle-bold">
              {errorMessage}
            </AuthNote>
          </Box>
        )}

        <Form methods={methods} onSubmit={onSubmit}>
          <Stack sx={{ mt: 3, gap: 2 }}>
            <AuthField
              name="password"
              label="KATA SANDI BARU"
              type={showPassword.value ? 'text' : 'password'}
              slotProps={{
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

            <Stack sx={{ gap: 1 }}>
              <Rule met={password.length >= 8} label="Minimal 8 karakter" />
              <Rule met={/\d/.test(password)} label="Ada angkanya" />
            </Stack>

            <AuthNote
              tone="warn"
              icon="solar:danger-triangle-bold"
              title="Semua perangkat bakal keluar"
            >
              Termasuk HP lain yang masih kebuka. Itu memang gunanya: kalau ada yang nebeng di akun
              lu, dia ikut keluar.
            </AuthNote>

            <AuthSubmit loading={isSubmitting} loadingIndicator="Menyimpan…">
              Simpan kata sandi
            </AuthSubmit>
          </Stack>
        </Form>
      </Box>

      <AuthFooter label="Kembali ke halaman masuk" href={paths.auth.signIn} />
    </>
  );
}
