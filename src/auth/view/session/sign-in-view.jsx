'use client';

import * as z from 'zod';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useBoolean } from 'minimal-shared/hooks';
import { zodResolver } from '@hookform/resolvers/zod';

import Box from '@mui/material/Box';
import Link from '@mui/material/Link';
import Stack from '@mui/material/Stack';
import IconButton from '@mui/material/IconButton';
import InputAdornment from '@mui/material/InputAdornment';

import { paths } from 'src/routes/paths';
import { useRouter } from 'src/routes/hooks';
import { RouterLink } from 'src/routes/components';

import { Iconify } from 'src/components/iconify';
import { Form, schemaUtils } from 'src/components/hook-form';

import { useAuthContext } from '../../hooks';
import { getErrorMessage } from '../../utils';
import { signInWithPassword } from '../../context/session';
import { AuthHead, AuthNote, AuthField, AuthFooter, AuthSubmit } from '../../components/auth-kit';

// ----------------------------------------------------------------------

export const SignInSchema = z.object({
  email: schemaUtils.email(),
  password: z
    .string()
    .min(1, { message: 'Kata sandi wajib diisi' })
    // Matches the backend's MIN_PASSWORD_LENGTH. This used to be 6, so
    // the form accepted a password the server then rejected, and the
    // rejection arrived as a generic error after a round trip.
    .min(8, { message: 'Kata sandi minimal 8 karakter' }),
});

// ----------------------------------------------------------------------

export function SignInView() {
  const router = useRouter();

  const showPassword = useBoolean();

  const { checkUserSession } = useAuthContext();

  const [errorMessage, setErrorMessage] = useState(null);

  const methods = useForm({
    resolver: zodResolver(SignInSchema),
    defaultValues: { email: '', password: '' },
  });

  const {
    handleSubmit,
    formState: { isSubmitting },
  } = methods;

  const onSubmit = handleSubmit(async (data) => {
    try {
      await signInWithPassword({ email: data.email, password: data.password });
      await checkUserSession?.();

      router.refresh();
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    }
  });

  return (
    <>
      <Box sx={{ flexGrow: 1 }}>
        <AuthHead mark title="Masuk" description="Lanjutin catatan keuangan lu." />

        {!!errorMessage && (
          <Box sx={{ mt: 2.5 }}>
            <AuthNote tone="bad" icon="solar:danger-triangle-bold">
              {errorMessage}
            </AuthNote>
          </Box>
        )}

        <Form methods={methods} onSubmit={onSubmit}>
          <Stack sx={{ mt: 3, gap: 2 }}>
            <AuthField name="email" label="EMAIL" type="email" />

            <AuthField
              name="password"
              label="KATA SANDI"
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

            <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}>
              <Link
                component={RouterLink}
                href={paths.auth.forgot}
                sx={{ py: 1, fontSize: 14, fontWeight: 800, color: 'primary.dark' }}
              >
                Lupa kata sandi?
              </Link>
            </Box>

            <AuthSubmit loading={isSubmitting} loadingIndicator="Masuk…">
              Masuk
            </AuthSubmit>
          </Stack>
        </Form>

        <Box sx={{ mt: 3 }}>
          <AuthNote icon="solar:shield-keyhole-bold-duotone">
            Nggak ada masuk lewat Google atau Facebook. Akun lu cuma ada di server ini, dan sesinya
            disimpan di cookie yang nggak bisa dibaca JavaScript.
          </AuthNote>
        </Box>
      </Box>

      <AuthFooter prompt="Belum punya akun?" label="Daftar" href={paths.auth.signUp} />
    </>
  );
}
