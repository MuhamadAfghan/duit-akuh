'use client';

import { useMemo, useState, useEffect, useCallback } from 'react';

import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Stack from '@mui/material/Stack';
import Alert from '@mui/material/Alert';
import Typography from '@mui/material/Typography';
import IconButton from '@mui/material/IconButton';

import { paths } from 'src/routes/paths';
import { useRouter } from 'src/routes/hooks';
import { RouterLink } from 'src/routes/components';

import { formatRupiah, formatRupiahPlain } from 'src/utils/format-money';

import { accountsApi, transactionsApi } from 'src/lib/api';

import { Iconify } from 'src/components/iconify';
import { SwipeConfirm } from 'src/components/swipe-confirm';

import { BoardNote, ChoiceChip, pressDigit, AmountKeypad, WalletPicker } from '../../common';

// ----------------------------------------------------------------------

const MODES = [
  { key: 'expense', label: 'Keluar' },
  { key: 'income', label: 'Masuk' },
  { key: 'transfer', label: 'Pindah' },
];

const PRESETS = [20000, 50000, 100000, 200000];

const CATEGORIES = ['Makan', 'Transport', 'Belanja', 'Tagihan'];

/** A fresh key per attempt, so a double tap posts once (AC04). */
function newOperationId() {
  return `catat-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

// ----------------------------------------------------------------------

export function CatatView() {
  const router = useRouter();

  const [mode, setMode] = useState('expense');
  const [digits, setDigits] = useState('');
  const [fromId, setFromId] = useState(null);
  const [toId, setToId] = useState(null);
  const [category, setCategory] = useState('Makan');

  const [accounts, setAccounts] = useState([]);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [operationId, setOperationId] = useState(newOperationId);

  useEffect(() => {
    accountsApi
      .list()
      .then((rows) => {
        const open = rows.filter((row) => !row.is_archived);
        setAccounts(open);
        setFromId((current) => current ?? open[0]?.id ?? null);
        setToId((current) => current ?? open[1]?.id ?? null);
      })
      .catch((err) => setError(err.message));
  }, []);

  const amount = Number(digits || 0);
  const isTransfer = mode === 'transfer';

  const draft = useMemo(() => {
    if (!amount) {
      return null;
    }

    if (mode === 'expense') {
      return fromId ? { type: 'expense', amount, from_account_id: fromId, category } : null;
    }

    if (mode === 'income') {
      return fromId ? { type: 'income', amount, to_account_id: fromId } : null;
    }

    return fromId && toId && fromId !== toId
      ? { type: 'transfer', amount, from_account_id: fromId, to_account_id: toId }
      : null;
  }, [mode, amount, fromId, toId, category]);

  // The impact is recomputed by the backend on every change, never here:
  // the UI is not allowed to do money arithmetic (FR06).
  useEffect(() => {
    if (!draft) {
      setPreview(null);
      return undefined;
    }

    let cancelled = false;

    transactionsApi
      .preview(draft)
      .then((result) => !cancelled && setPreview(result))
      .catch(() => !cancelled && setPreview(null));

    return () => {
      cancelled = true;
    };
  }, [draft]);

  const press = useCallback((key) => {
    setError(null);
    setDigits((current) => pressDigit(current, key));
  }, []);

  const save = async () => {
    if (!draft || busy) {
      return;
    }

    setBusy(true);
    setError(null);

    try {
      await transactionsApi.create(draft, operationId);
      router.push(paths.data);
    } catch (err) {
      setError(err.message);
      // A failed attempt gets its own key: retrying must not be read as
      // a replay of something that never landed.
      setOperationId(newOperationId());
    } finally {
      setBusy(false);
    }
  };

  const picker = accounts.filter((account) =>
    mode === 'income' ? account.type !== 'credit_card' : true
  );

  return (
    <Box sx={{ flex: '1 1 auto', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      <Box sx={{ flexShrink: 0, py: 1.5, display: 'flex', justifyContent: 'center' }}>
        <IconButton
          component={RouterLink}
          href={paths.chat}
          aria-label="Tutup, kembali ke chat"
          sx={{ width: 44, height: 44, bgcolor: 'common.white', color: 'text.primary' }}
        >
          <Iconify icon="mingcute:close-line" width={22} />
        </IconButton>
      </Box>

      <Card
        sx={{
          flex: '1 1 auto',
          minHeight: 0,
          display: 'flex',
          borderRadius: '28px 28px 0 0',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        <Box sx={{ pt: 1.25, display: 'flex', justifyContent: 'center' }}>
          <Box sx={{ width: 40, height: 4, borderRadius: 999, bgcolor: 'grey.300' }} />
        </Box>

        <Box sx={{ px: 2.5, pt: 0.75 }}>
          <Typography sx={{ fontSize: 20, fontWeight: 800, letterSpacing: '-0.02em' }}>
            Catat manual
          </Typography>

          <Box
            role="group"
            aria-label="Jenis catatan"
            sx={{
              mt: 1.75,
              p: 0.5,
              gap: 0.5,
              display: 'grid',
              borderRadius: 999,
              bgcolor: 'grey.100',
              gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
            }}
          >
            {MODES.map((item) => {
              const active = mode === item.key;

              return (
                <Box
                  key={item.key}
                  component="button"
                  type="button"
                  aria-pressed={active}
                  onClick={() => setMode(item.key)}
                  sx={{
                    border: 'none',
                    minHeight: 40,
                    fontSize: 14,
                    fontWeight: 800,
                    cursor: 'pointer',
                    borderRadius: 999,
                    color: active ? 'common.white' : 'text.secondary',
                    bgcolor: active ? 'grey.800' : 'transparent',
                  }}
                >
                  {item.label}
                </Box>
              );
            })}
          </Box>
        </Box>

        <Box sx={{ flex: '1 1 auto', minHeight: 0, overflowY: 'auto', px: 2.5, pt: 2 }}>
          <Stack direction="row" sx={{ gap: 1, alignItems: 'baseline' }}>
            <Typography sx={{ fontSize: 20, fontWeight: 800, color: 'grey.500' }}>Rp</Typography>
            <Typography
              sx={{
                fontSize: 44,
                lineHeight: '48px',
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
                label={`${value / 1000}rb`}
                onClick={() => setDigits(String(value))}
              />
            ))}
          </Stack>

          <SectionCaps>{isTransfer ? 'DARI KANTONG' : 'KANTONG'}</SectionCaps>
          <WalletPicker
            accounts={picker}
            selectedId={fromId}
            onSelect={setFromId}
            label={isTransfer ? 'Dari kantong' : 'Kantong'}
          />

          {isTransfer && (
            <>
              <SectionCaps>KE KANTONG</SectionCaps>
              <WalletPicker
                label="Ke kantong"
                selectedId={toId}
                onSelect={setToId}
                accounts={picker.filter((account) => account.id !== fromId)}
              />
              <Box sx={{ mt: 1.5 }}>
                <BoardNote tone="info">
                  Uang yang pindah nggak dihitung sebagai pengeluaran. Kalau ada biaya admin, catat
                  terpisah lewat chat.
                </BoardNote>
              </Box>
            </>
          )}

          {mode === 'expense' && (
            <>
              <SectionCaps>KATEGORI</SectionCaps>
              <Stack direction="row" sx={{ gap: 1, overflowX: 'auto', pb: 0.5 }}>
                {CATEGORIES.map((name) => (
                  <ChoiceChip
                    key={name}
                    label={name}
                    active={category === name}
                    onClick={() => setCategory(name)}
                  />
                ))}
              </Stack>
            </>
          )}

          {preview && (
            <Box sx={{ mt: 2 }}>
              <SectionCaps>DAMPAK</SectionCaps>
              <Card variant="outlined" sx={{ p: 1.75, borderRadius: 2 }}>
                {preview.impact.map((row) => (
                  <Stack
                    key={row.account_id}
                    direction="row"
                    sx={{ py: 0.4, gap: 2, justifyContent: 'space-between' }}
                  >
                    <Typography sx={{ fontSize: 13, fontWeight: 600, color: 'text.secondary' }}>
                      {accounts.find((a) => a.id === row.account_id)?.name ?? 'Kantong'}
                    </Typography>
                    <Typography
                      sx={{ fontSize: 13, fontWeight: 800, fontVariantNumeric: 'tabular-nums' }}
                    >
                      {formatRupiah(row.before)} → {formatRupiah(row.after)}
                    </Typography>
                  </Stack>
                ))}

                {preview.would_overdraw && (
                  <Alert severity="warning" sx={{ mt: 1 }}>
                    Saldonya bakal minus. Cek lagi sebelum disimpan.
                  </Alert>
                )}
              </Card>
            </Box>
          )}

          {error && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {error}
            </Alert>
          )}
        </Box>

        <Box sx={{ flexShrink: 0, px: 2.5, pt: 1, pb: 2 }}>
          <AmountKeypad onPress={press} />

          <Box sx={{ mt: 1.5 }}>
            <SwipeConfirm
              label="Geser untuk simpan"
              busy={busy}
              disabled={!draft}
              onConfirm={save}
            />
          </Box>

          <Typography
            sx={{
              mt: 1.25,
              fontSize: 12,
              fontWeight: 600,
              textAlign: 'center',
              color: 'text.secondary',
            }}
          >
            Dampaknya dihitung server, sama seperti lewat chat.
          </Typography>
        </Box>
      </Card>
    </Box>
  );
}

// ----------------------------------------------------------------------

function SectionCaps({ children }) {
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
