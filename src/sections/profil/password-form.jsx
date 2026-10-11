'use client';

import * as z from 'zod';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useBoolean } from 'minimal-shared/hooks';
import { zodResolver } from '@hookform/resolvers/zod';

import Box from '@mui/material/Box';
import Alert from '@mui/material/Alert';
import Stack from '@mui/material/Stack';
import Dialog from '@mui/material/Dialog';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import InputAdornment from '@mui/material/InputAdornment';

import { authApi } from 'src/lib/api';

import { Iconify } from 'src/components/iconify';
import { Form, Field } from 'src/components/hook-form';

import { Rule } from 'src/auth/components/rule';
import { useAuthContext } from 'src/auth/hooks';

import { BoardNote } from '../common';

// ----------------------------------------------------------------------

/** Mirrors the backend's own limits, so a rejection is never a surprise. */
export const PasswordSchema = z.object({
  current_password: z.string().min(1, { message: 'Kata sandi sekarang wajib diisi' }),
  new_password: z
    .string()
    .min(1, { message: 'Kata sandi baru wajib diisi' })
    .min(8, { message: 'Kata sandi minimal 8 karakter' })
    .max(256),
});

// ----------------------------------------------------------------------

/**
 * Changing a password from inside the app.
 *
 * The backend revokes every session on success, this one included, so
 * there is no "saved" state to return to — the request that succeeds
 * is also the request that signs the user out. Refreshing the auth
 * context is what moves them on: the guard sees an unauthenticated
 * context and sends them to sign-in, exactly as it would after any
 * other expired session.
 */
export function PasswordForm({ open, onClose }) {
  const { checkUserSession } = useAuthContext();

  const showCurrent = useBoolean();
  const showNew = useBoolean();

  const [errorMessage, setErrorMessage] = useState(null);

  const methods = useForm({
    resolver: zodResolver(PasswordSchema),
    defaultValues: { current_password: '', new_password: '' },
  });

  const {
    watch,
    handleSubmit,
    formState: { isSubmitting },
  } = methods;

  const newPassword = watch('new_password');

  const onSubmit = handleSubmit(async (data) => {
    setErrorMessage(null);

    try {
      await authApi.changePassword(data.current_password, data.new_password);
      await checkUserSession?.();
    } catch (error) {
      setErrorMessage(error.message);
    }
  });

  return (
    <Dialog
      fullWidth
      maxWidth="xs"
      open={open}
      onClose={isSubmitting ? undefined : onClose}
      slotProps={{ paper: { sx: { borderRadius: 3 } } }}
    >
      <Form methods={methods} onSubmit={onSubmit}>
        <DialogTitle sx={{ pb: 1 }}>Ganti kata sandi</DialogTitle>

        <DialogContent sx={{ pb: 1 }}>
          {!!errorMessage && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {errorMessage}
            </Alert>
          )}

          <Box sx={{ pt: 1, gap: 2.5, display: 'flex', flexDirection: 'column' }}>
            <Field.Text
              name="current_password"
              label="Kata sandi sekarang"
              type={showCurrent.value ? 'text' : 'password'}
              slotProps={{
                input: {
                  endAdornment: (
                    <RevealButton shown={showCurrent.value} onToggle={showCurrent.onToggle} />
                  ),
                },
              }}
            />

            <Field.Text
              name="new_password"
              label="Kata sandi baru"
              type={showNew.value ? 'text' : 'password'}
              slotProps={{
                input: {
                  endAdornment: <RevealButton shown={showNew.value} onToggle={showNew.onToggle} />,
                },
              }}
            />

            <Stack sx={{ gap: 1 }}>
              <Rule met={newPassword.length >= 8} label="Minimal 8 karakter" />
              <Rule met={/\d/.test(newPassword)} label="Ada angkanya" />
            </Stack>

            <BoardNote tone="warn">
              Semua perangkat bakal keluar, termasuk HP ini. Itu memang gunanya: kalau ada yang
              nebeng di akun lu, dia ikut keluar. Habis ini lu masuk lagi pakai yang baru.
            </BoardNote>
          </Box>
        </DialogContent>

        <DialogActions sx={{ px: 3, pb: 3 }}>
          <Button color="inherit" onClick={onClose} disabled={isSubmitting} sx={{ minHeight: 44 }}>
            Batal
          </Button>
          <Button
            type="submit"
            variant="contained"
            loading={isSubmitting}
            loadingIndicator="Menyimpan…"
            sx={{ minHeight: 44 }}
          >
            Simpan
          </Button>
        </DialogActions>
      </Form>
    </Dialog>
  );
}

// ----------------------------------------------------------------------

function RevealButton({ shown, onToggle }) {
  return (
    <InputAdornment position="end">
      <IconButton
        edge="end"
        onClick={onToggle}
        aria-label={shown ? 'Sembunyikan kata sandi' : 'Tampilkan kata sandi'}
      >
        <Iconify icon={shown ? 'solar:eye-bold' : 'solar:eye-closed-bold'} />
      </IconButton>
    </InputAdornment>
  );
}
