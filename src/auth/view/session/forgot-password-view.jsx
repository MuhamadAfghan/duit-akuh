'use client';

import * as z from 'zod';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';

import Box from '@mui/material/Box';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';

import { paths } from 'src/routes/paths';
import { useRouter } from 'src/routes/hooks';

import { authApi } from 'src/lib/api';

import { Form, Field, schemaUtils } from 'src/components/hook-form';

import { getErrorMessage } from '../../utils';
import { FormHead } from '../../components/form-head';
import { FormReturnLink } from '../../components/form-return-link';

// ----------------------------------------------------------------------

export const ForgotPasswordSchema = z.object({
  email: schemaUtils.email(),
});

/**
 * Where the next screen reads the address from.
 *
 * Not a query parameter. An email address in the URL ends up in browser
 * history, in any server access log, and in whatever a screenshot
 * captures — all for the sake of one line of copy.
 */
export const RESET_EMAIL_KEY = 'lega:reset-email';

// ----------------------------------------------------------------------

export function ForgotPasswordView() {
  const router = useRouter();

  const [errorMessage, setErrorMessage] = useState(null);

  const methods = useForm({
    resolver: zodResolver(ForgotPasswordSchema),
    defaultValues: { email: '' },
  });

  const {
    handleSubmit,
    formState: { isSubmitting },
  } = methods;

  const onSubmit = handleSubmit(async (data) => {
    try {
      await authApi.forgotPassword(data.email);

      try {
        sessionStorage.setItem(RESET_EMAIL_KEY, data.email);
      } catch {
        // Private mode, or storage is full. The next screen copes.
      }

      router.push(paths.auth.checkEmail);
    } catch (error) {
      // A 429 is the only thing the server will refuse with. Everything
      // else, including an address nobody has registered, comes back
      // 202 on purpose.
      setErrorMessage(getErrorMessage(error));
    }
  });

  return (
    <>
      <FormHead
        title="Lupa kata sandi"
        description="Masukin email akunnya. Kalau terdaftar, kami kirim tautan buat bikin kata sandi baru."
        sx={{ textAlign: { xs: 'center', md: 'left' } }}
      />

      {!!errorMessage && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {errorMessage}
        </Alert>
      )}

      <Form methods={methods} onSubmit={onSubmit}>
        <Box sx={{ gap: 3, display: 'flex', flexDirection: 'column' }}>
          <Field.Text name="email" label="Email" slotProps={{ inputLabel: { shrink: true } }} />

          <Button
            fullWidth
            color="inherit"
            size="large"
            type="submit"
            variant="contained"
            loading={isSubmitting}
            loadingIndicator="Mengirim…"
          >
            Kirim tautan
          </Button>
        </Box>
      </Form>

      <Box
        sx={{
          mt: 3,
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
        <span>Tautannya berlaku 60 menit dan cuma bisa dipakai sekali.</span>
        <span>
          Kata sandi lama tetap jalan sampai yang baru dipasang. Minta tautan nggak bikin akun
          kekunci.
        </span>
      </Box>

      <FormReturnLink href={paths.auth.signIn} label="Kembali ke halaman masuk" />
    </>
  );
}
