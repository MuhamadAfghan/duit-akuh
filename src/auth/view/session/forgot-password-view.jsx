'use client';

import * as z from 'zod';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';

import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';

import { paths } from 'src/routes/paths';
import { useRouter } from 'src/routes/hooks';

import { authApi } from 'src/lib/api';

import { Form, schemaUtils } from 'src/components/hook-form';

import { getErrorMessage } from '../../utils';
import { AuthHead, AuthNote, AuthField, AuthFooter, AuthSubmit } from '../../components/auth-kit';

// ----------------------------------------------------------------------

export const ForgotPasswordSchema = z.object({ email: schemaUtils.email() });

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
      // A 429 is the only refusal the server will give. Everything
      // else, an unregistered address included, comes back 202.
      setErrorMessage(getErrorMessage(error));
    }
  });

  return (
    <>
      <Box sx={{ flexGrow: 1 }}>
        <AuthHead
          title="Lupa kata sandi"
          description="Masukin email akunnya. Kalau terdaftar, kami kirim tautan buat bikin kata sandi baru."
        />

        {!!errorMessage && (
          <Box sx={{ mt: 2.5 }}>
            <AuthNote tone="bad" icon="solar:danger-triangle-bold">
              {errorMessage}
            </AuthNote>
          </Box>
        )}

        <Form methods={methods} onSubmit={onSubmit}>
          <Stack sx={{ mt: 3, gap: 2.5 }}>
            <AuthField name="email" label="EMAIL" type="email" />

            <AuthSubmit loading={isSubmitting} loadingIndicator="Mengirim…">
              Kirim tautan
            </AuthSubmit>
          </Stack>
        </Form>

        <Stack sx={{ mt: 3, gap: 1.5 }}>
          <AuthNote icon="lega:clock">
            Tautannya berlaku <strong>60 menit</strong> dan cuma bisa dipakai sekali.
          </AuthNote>

          <AuthNote icon="solar:shield-keyhole-bold-duotone">
            Kata sandi lama tetap jalan sampai yang baru dipasang. Minta tautan nggak bikin akun
            kekunci.
          </AuthNote>
        </Stack>
      </Box>

      <AuthFooter prompt="Inget kata sandinya?" label="Masuk" href={paths.auth.signIn} />
    </>
  );
}
