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
import { useRouter } from 'src/routes/hooks';

import { Iconify } from 'src/components/iconify';
import { Form, schemaUtils } from 'src/components/hook-form';

import { Rule } from '../../components/rule';
import { useAuthContext } from '../../hooks';
import { getErrorMessage } from '../../utils';
import { signUp } from '../../context/session';
import { AuthHead, AuthNote, AuthField, AuthFooter, AuthSubmit } from '../../components/auth-kit';

// ----------------------------------------------------------------------

export const SignUpSchema = z.object({
  email: schemaUtils.email(),
  password: z
    .string()
    .min(1, { message: 'Kata sandi wajib diisi' })
    // Matches the backend's MIN_PASSWORD_LENGTH.
    .min(8, { message: 'Kata sandi minimal 8 karakter' }),
});

// ----------------------------------------------------------------------

export function SignUpView() {
  const router = useRouter();

  const showPassword = useBoolean();

  const { checkUserSession } = useAuthContext();

  const [errorMessage, setErrorMessage] = useState(null);

  const methods = useForm({
    resolver: zodResolver(SignUpSchema),
    defaultValues: { email: '', password: '' },
  });

  const {
    watch,
    handleSubmit,
    formState: { isSubmitting },
  } = methods;

  const password = watch('password');

  const onSubmit = handleSubmit(async (data) => {
    try {
      await signUp({ email: data.email, password: data.password });
      await checkUserSession?.();

      router.refresh();
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    }
  });

  return (
    <>
      <Box sx={{ flexGrow: 1 }}>
        <AuthHead title="Bikin akun" description="Semenit doang, terus langsung bisa nyatet." />

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

            {/* Live, under the field it describes. Rules that only appear
                after a rejection are a quiz, not guidance. */}
            <Stack sx={{ gap: 1 }}>
              <Rule met={password.length >= 8} label="Minimal 8 karakter" />
              <Rule met={/\d/.test(password)} label="Ada angkanya" />
            </Stack>

            <AuthSubmit loading={isSubmitting} loadingIndicator="Bikin akun…">
              Bikin akun
            </AuthSubmit>
          </Stack>
        </Form>

        <Box sx={{ mt: 3 }}>
          <AuthNote
            tone="good"
            icon="solar:shield-check-bold"
            title="Catatan lu nggak ke mana-mana"
          >
            Teks, struk, dan suara diproses di server sendiri, bukan dikirim ke layanan AI pihak
            ketiga. Kalau suatu saat pindah ke AI awan, lu bakal ditanya dulu.
          </AuthNote>
        </Box>

        <Box
          sx={{ mt: 2, fontSize: 12, lineHeight: 1.5, fontWeight: 600, color: 'text.secondary' }}
        >
          Akun diatur ke rupiah dan zona waktu Asia/Jakarta. Bisa diganti nanti.
        </Box>
      </Box>

      <AuthFooter prompt="Udah punya akun?" label="Masuk" href={paths.auth.signIn} />
    </>
  );
}
