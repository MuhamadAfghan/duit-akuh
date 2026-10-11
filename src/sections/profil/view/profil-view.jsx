'use client';

import { useState, useCallback } from 'react';
import { useBoolean } from 'minimal-shared/hooks';

import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Alert from '@mui/material/Alert';
import Dialog from '@mui/material/Dialog';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';

import { CONFIG } from 'src/global-config';

import { Iconify } from 'src/components/iconify';

import { useAuthContext } from 'src/auth/hooks';
import { signOut } from 'src/auth/context/session';

import { PasswordForm } from '../password-form';
import {
  ListRow,
  ListCard,
  BoardBody,
  BoardNote,
  RowAvatar,
  BoardTitle,
  RowDivider,
  SectionLabel,
} from '../../common';

// ----------------------------------------------------------------------

/**
 * The account surface, and the only way out of the app.
 *
 * It holds no money figures on purpose. Everything here is about the
 * account rather than the ledger — Ringkasan already answers "how much
 * do I have", and repeating a balance in a second place is how two
 * screens start disagreeing.
 *
 * There is no row that only looks like a control. A name, a photo and
 * a notification switch would all fit the shape of this page, but the
 * backend stores an email, a timezone and nothing else, so the page
 * shows an email and a timezone.
 */
export function ProfilView() {
  const { user, checkUserSession } = useAuthContext();

  const passwordForm = useBoolean();
  const confirmSignOut = useBoolean();

  const [signingOut, setSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState(null);

  const handleSignOut = useCallback(async () => {
    setSigningOut(true);
    setSignOutError(null);

    try {
      await signOut();
      // The guard watches the auth context, so refreshing it is what
      // actually moves the user to sign-in. No router push needed, and
      // none that could race it.
      await checkUserSession?.();
    } catch (error) {
      // Offline, most likely. Saying "keluar" while the session is
      // still alive on the server would be a lie the next tap exposes.
      setSigningOut(false);
      setSignOutError(error.message);
    }
  }, [checkUserSession]);

  return (
    <>
      <BoardTitle title="Saya" />

      <BoardBody>
        <IdentityCard email={user?.email} timezone={user?.timezone} />

        <SectionLabel>AKUN</SectionLabel>

        <ListCard>
          <ListRow
            avatar={<RowAvatar icon="lega:shield" tone="green" />}
            title="Keamanan & kata sandi"
            note="Ganti kata sandi, keluarkan semua perangkat"
            onClick={passwordForm.onTrue}
            action={<Chevron />}
          />

          <RowDivider />

          <ListRow
            avatar={<RowAvatar icon="lega:download" tone="blue" />}
            title="Ekspor semua transaksi"
            note="Berkas CSV, semua periode"
            href="/srv/export/transactions.csv?period=semua"
            external
            action={<Chevron />}
          />
        </ListCard>

        <SectionLabel>KELUAR</SectionLabel>

        <ListCard>
          <ListRow
            avatar={<RowAvatar icon="lega:logout" tone="red" />}
            title={
              <Box component="span" sx={{ color: 'error.main' }}>
                Keluar dari akun ini
              </Box>
            }
            note="Catatan lu tetap tersimpan"
            onClick={confirmSignOut.onTrue}
            action={<Chevron />}
          />
        </ListCard>

        <BoardNote>
          {CONFIG.appName} v{CONFIG.appVersion}. Catatan, struk dan suara lu diolah di server
          sendiri, bukan dikirim ke layanan AI pihak ketiga.
        </BoardNote>
      </BoardBody>

      <PasswordForm open={passwordForm.value} onClose={passwordForm.onFalse} />

      <Dialog
        fullWidth
        maxWidth="xs"
        open={confirmSignOut.value}
        onClose={signingOut ? undefined : confirmSignOut.onFalse}
        slotProps={{ paper: { sx: { borderRadius: 3 } } }}
      >
        <DialogTitle sx={{ pb: 1 }}>Keluar dari akun ini?</DialogTitle>

        <DialogContent sx={{ pb: 1 }}>
          {!!signOutError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {signOutError}
            </Alert>
          )}

          <Typography sx={{ fontSize: 14, fontWeight: 600, color: 'text.secondary' }}>
            Nggak ada data yang hilang — semuanya nunggu di sini waktu lu masuk lagi. Draft chat
            yang belum dikirim ikut kehapus, biar nggak kebaca akun berikutnya di HP ini.
          </Typography>
        </DialogContent>

        <DialogActions sx={{ px: 3, pb: 3 }}>
          <Button
            color="inherit"
            onClick={confirmSignOut.onFalse}
            disabled={signingOut}
            sx={{ minHeight: 44 }}
          >
            Batal
          </Button>
          <Button
            color="error"
            variant="contained"
            onClick={handleSignOut}
            loading={signingOut}
            loadingIndicator="Keluar…"
            sx={{ minHeight: 44 }}
          >
            Keluar
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

// ----------------------------------------------------------------------

/**
 * Who is signed in, in brand green.
 *
 * The initials come from the email because that is the only name the
 * account has. Two letters, not three: an email local part is not a
 * wallet name, and "AIL" reads as a crop where "AI" reads as initials.
 */
function IdentityCard({ email, timezone }) {
  return (
    <Card
      sx={{
        p: 3,
        gap: 1.25,
        display: 'flex',
        borderRadius: 3,
        textAlign: 'center',
        alignItems: 'center',
        flexDirection: 'column',
        bgcolor: 'primary.main',
        color: 'primary.contrastText',
      }}
    >
      <Box
        aria-hidden
        sx={{
          width: 72,
          height: 72,
          fontSize: 26,
          display: 'grid',
          fontWeight: 800,
          borderRadius: '50%',
          placeItems: 'center',
          letterSpacing: '0.02em',
          bgcolor: 'rgba(255,255,255,0.22)',
        }}
      >
        {emailInitials(email)}
      </Box>

      <Typography
        sx={{
          fontSize: 17,
          fontWeight: 800,
          lineHeight: 1.35,
          letterSpacing: '-0.01em',
          // A long address must wrap rather than widen the card: the
          // shell has no horizontal scroll at 320px and must not grow
          // one here (FR17).
          overflowWrap: 'anywhere',
        }}
      >
        {email ?? '—'}
      </Typography>

      <Box
        sx={{
          px: 1.5,
          py: 0.5,
          fontSize: 12,
          fontWeight: 700,
          borderRadius: 999,
          bgcolor: 'rgba(255,255,255,0.18)',
        }}
      >
        {timezone ?? 'Asia/Jakarta'}
      </Box>
    </Card>
  );
}

function emailInitials(email) {
  const local = (email ?? '').split('@')[0];
  const parts = local.split(/[^a-zA-Z0-9]+/).filter(Boolean);

  if (!parts.length) {
    return '?';
  }

  const letters = parts.length > 1 ? parts[0][0] + parts[1][0] : parts[0].slice(0, 2);

  return letters.toUpperCase();
}

function Chevron() {
  return <Iconify icon="lega:arrow-right" width={18} sx={{ color: 'text.disabled' }} />;
}
