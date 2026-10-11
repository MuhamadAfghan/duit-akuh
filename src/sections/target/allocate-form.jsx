'use client';

import { useState, useEffect } from 'react';

import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Drawer from '@mui/material/Drawer';
import Typography from '@mui/material/Typography';

import { formatRupiah, formatRupiahPlain } from 'src/utils/format-money';

import { goalsApi, accountsApi } from 'src/lib/api';

import { SwipeConfirm } from 'src/components/swipe-confirm';

import { BoardNote, ChoiceChip, pressDigit, AmountKeypad, WalletPicker } from '../common';

// ----------------------------------------------------------------------

const PRESETS = [100_000, 500_000, 1_000_000, 5_000_000];

/**
 * Board 08 — "ALOKASI — DITANDAI, BUKAN DIPINDAH".
 *
 * Earmarking is the one action in the app that looks like moving money
 * and isn't, so the sheet is built around saying so: the wallet's
 * balance is shown unchanged, and what drops is only the free-to-spend
 * figure.
 *
 * Two things the endpoint does that the copy has to admit:
 *
 * - The amount **replaces** this goal's mark on that wallet instead of
 *   adding to it, so the field opens on the current mark and the label
 *   says "jadi", not "tambah".
 * - A mark cannot be zero. Clearing one is a separate call, which is
 *   why "Lepas tanda" is its own button rather than typing 0.
 *
 * No arithmetic happens here. The limit — total marks on a wallet may
 * not exceed its positive balance (AC05) — is the server's to enforce,
 * and its refusal is shown as it comes.
 */
export function AllocateForm({ goal, open, onClose, onSaved }) {
  const [accounts, setAccounts] = useState([]);
  const [accountId, setAccountId] = useState(null);
  const [digits, setDigits] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    let cancelled = false;

    setError(null);
    setDigits('');

    accountsApi
      .list()
      .then((rows) => {
        if (cancelled) {
          return;
        }

        // A credit card holds no money, and a limit is not money
        // either (FR01/FR09), so neither can back a goal.
        const usable = rows.filter((row) => !row.is_archived && row.type !== 'credit_card');

        setAccounts(usable);
        setAccountId((current) => current ?? usable[0]?.id ?? null);
      })
      .catch((err) => !cancelled && setError(err.message));

    return () => {
      cancelled = true;
    };
  }, [open]);

  const wallet = accounts.find((account) => account.id === accountId);
  const marked = goal?.allocations?.find((row) => row.account_id === accountId)?.amount ?? 0;

  // Opening on the current mark is what makes "replaces" readable: you
  // see the number you are about to overwrite.
  useEffect(() => {
    setDigits(marked ? String(marked) : '');
  }, [marked, accountId]);

  const amount = Number(digits || 0);

  const save = async () => {
    if (!amount || !accountId || busy) {
      return;
    }

    setBusy(true);
    setError(null);

    try {
      await goalsApi.allocate(goal.id, accountId, amount);
      onSaved?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const release = async () => {
    setBusy(true);
    setError(null);

    try {
      await goalsApi.release(goal.id, accountId);
      onSaved?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Drawer
      anchor="bottom"
      open={open}
      onClose={busy ? undefined : onClose}
      slotProps={{
        paper: {
          sx: {
            width: 1,
            // The shell is a phone column even on a desktop; a sheet
            // spanning the whole window would not belong to it.
            maxWidth: 720,
            marginInline: 'auto',
            maxHeight: '90dvh',
            borderRadius: '28px 28px 0 0',
          },
        },
      }}
    >
      <Box sx={{ pt: 1.25, display: 'flex', justifyContent: 'center' }}>
        <Box sx={{ width: 40, height: 4, borderRadius: 999, bgcolor: 'grey.300' }} />
      </Box>

      <Box
        sx={{
          px: 2.5,
          pt: 1.5,
          // Without an explicit zero min-height this flex child refuses
          // to shrink, so the sheet grows past its own maxHeight instead
          // of scrolling.
          minHeight: 0,
          overflowY: 'auto',
          pb: 'calc(20px + env(safe-area-inset-bottom))',
        }}
      >
        <Typography sx={{ fontSize: 15, fontWeight: 800 }}>
          Sisihkan ke target {goal?.name}
        </Typography>

        <Stack direction="row" sx={{ mt: 1, gap: 1, alignItems: 'baseline' }}>
          <Typography sx={{ fontSize: 16, fontWeight: 800, color: 'grey.500' }}>Rp</Typography>
          <Typography
            sx={{
              fontSize: 32,
              lineHeight: '36px',
              fontWeight: 800,
              letterSpacing: '-0.02em',
              fontVariantNumeric: 'tabular-nums',
              color: amount ? 'text.primary' : 'grey.400',
            }}
          >
            {formatRupiahPlain(amount)}
          </Typography>
        </Stack>

        <Stack direction="row" sx={{ mt: 1.5, gap: 1, overflowX: 'auto', pb: 0.5 }}>
          {PRESETS.map((value) => (
            <ChoiceChip
              key={value}
              label={formatRupiahPlain(value)}
              active={amount === value}
              onClick={() => setDigits(String(value))}
            />
          ))}
        </Stack>

        <Caps>DARI KANTONG</Caps>
        <WalletPicker
          label="Dari kantong"
          accounts={accounts}
          selectedId={accountId}
          onSelect={setAccountId}
        />

        {wallet && (
          <Stack sx={{ mt: 2, gap: 0.9 }}>
            <Typography sx={{ fontSize: 13, fontWeight: 600, color: 'grey.700' }}>
              Saldo {wallet.name}{' '}
              <Box component="strong" sx={{ color: 'text.primary' }}>
                tetap
              </Box>{' '}
              <Box
                component="span"
                sx={{ fontWeight: 800, color: 'text.primary', fontVariantNumeric: 'tabular-nums' }}
              >
                {formatRupiahPlain(wallet.balance)}
              </Box>
            </Typography>

            {marked > 0 && (
              <Typography sx={{ fontSize: 13, fontWeight: 600, color: 'grey.700' }}>
                Sudah ditandai dari kantong ini{' '}
                <Box component="span" sx={{ fontWeight: 800, color: 'text.primary' }}>
                  {formatRupiahPlain(marked)}
                </Box>{' '}
                — angka di atas menggantinya, bukan menambah.
              </Typography>
            )}
          </Stack>
        )}

        <Box sx={{ mt: 1.5 }}>
          <BoardNote>
            Uangnya cuma ditandai biar nggak kepakai. Total aset nggak naik, nggak turun — yang
            berubah cuma angka <strong>bebas pakai</strong>.
          </BoardNote>
        </Box>

        {goal?.shortfall > 0 && (
          <Typography sx={{ mt: 1.25, fontSize: 12, fontWeight: 600, color: 'text.secondary' }}>
            Kurang {formatRupiah(goal.shortfall)} lagi buat nutup target ini.
          </Typography>
        )}

        {error && (
          <Alert severity="error" sx={{ mt: 2 }}>
            {error}
          </Alert>
        )}

        {!accounts.length && !error && (
          <Box sx={{ mt: 2 }}>
            <BoardNote tone="warn">
              Belum ada kantong yang bisa dipakai. Bikin dulu di Kantong.
            </BoardNote>
          </Box>
        )}

        <Box sx={{ mt: 2 }}>
          <AmountKeypad onPress={(key) => setDigits((current) => pressDigit(current, key))} />
        </Box>

        <Box sx={{ mt: 1.5 }}>
          <SwipeConfirm
            label="Geser untuk sisihkan"
            busy={busy}
            disabled={!amount || !accountId}
            onConfirm={save}
          />
        </Box>

        <Stack direction="row" sx={{ mt: 1, gap: 1 }}>
          <Button
            fullWidth
            onClick={onClose}
            disabled={busy}
            sx={{ minHeight: 44, fontWeight: 700, color: 'text.secondary' }}
          >
            Batal
          </Button>

          {marked > 0 && (
            <Button
              fullWidth
              onClick={release}
              disabled={busy}
              sx={{ minHeight: 44, fontWeight: 700, color: '#8E1212' }}
            >
              Lepas tanda
            </Button>
          )}
        </Stack>
      </Box>
    </Drawer>
  );
}

// ----------------------------------------------------------------------

function Caps({ children }) {
  return (
    <Typography
      sx={{
        mt: 2.25,
        mb: 1.25,
        fontSize: 12,
        fontWeight: 800,
        letterSpacing: '0.06em',
        color: 'text.secondary',
      }}
    >
      {children}
    </Typography>
  );
}
