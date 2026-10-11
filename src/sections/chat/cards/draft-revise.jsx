'use client';

import { useMemo, useState, useCallback } from 'react';

import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Button from '@mui/material/Button';
import InputBase from '@mui/material/InputBase';
import Typography from '@mui/material/Typography';

import { Iconify } from 'src/components/iconify';

import { ChoiceChip, WalletPicker } from '../../common';

// ----------------------------------------------------------------------

/**
 * Which account fields each kind actually has.
 *
 * Mirrors `ACCOUNT_FIELDS` in `app/services/chat/revise.py`. Two copies
 * of one fact, which is a cost — but the server has to refuse a bad
 * field whatever the client believes, and the client has to know which
 * pickers to draw. The server is the one that decides; this only
 * decides what to render.
 */
const ACCOUNT_FIELDS = {
  expense: [{ key: 'from_account_id', label: 'Dari kantong' }],
  income: [{ key: 'to_account_id', label: 'Masuk ke kantong' }],
  refund: [{ key: 'to_account_id', label: 'Masuk ke kantong' }],
  transfer: [
    { key: 'from_account_id', label: 'Dari kantong' },
    { key: 'to_account_id', label: 'Ke kantong' },
  ],
  card_payment: [
    { key: 'from_account_id', label: 'Bayar dari' },
    { key: 'card_account_id', label: 'Kartu yang dibayar' },
  ],
};

/** The same four manual entry offers, so the two screens agree. */
const CATEGORIES = ['Makan', 'Transport', 'Belanja', 'Tagihan'];

const digitsOf = (value) => String(value ?? '').replace(/\D/g, '');

// ----------------------------------------------------------------------

/**
 * Editing a draft before it is committed.
 *
 * Nothing here computes money. The form collects changed fields and
 * hands them to the server, which re-validates every one and recomputes
 * the impact with the functions that drew the first card — so a revised
 * preview and a fresh one cannot disagree.
 *
 * Only changed fields are sent. A patch of everything would make an
 * untouched category look like a deliberate re-assertion of it, and the
 * server refuses a patch that changes nothing, which is the check that
 * catches a form submitting itself.
 */
export function DraftRevise({ card, accounts, saving, error, onApply, onBack }) {
  // Memoised because both feed a useMemo below: a fresh {} or [] every
  // render would recompute the patch on every keystroke of every field.
  const payload = useMemo(() => card.payload ?? {}, [card.payload]);
  const pickers = useMemo(() => ACCOUNT_FIELDS[card.kind] ?? [], [card.kind]);

  const [amount, setAmount] = useState(() => digitsOf(payload.amount));
  const [category, setCategory] = useState(payload.category ?? '');
  const [note, setNote] = useState(payload.note ?? '');
  const [wallets, setWallets] = useState(() =>
    Object.fromEntries(
      (ACCOUNT_FIELDS[card.kind] ?? []).map(({ key }) => [key, payload[key] ?? null])
    )
  );

  // A category the model picked that is not one of the presets would
  // otherwise vanish the moment this form opened.
  const categories = useMemo(
    () => (category && !CATEGORIES.includes(category) ? [category, ...CATEGORIES] : CATEGORIES),
    [category]
  );

  const patch = useMemo(() => {
    const next = {};

    const parsed = Number(amount);

    if (amount && parsed !== payload.amount) {
      next.amount = parsed;
    }

    if ((category || '') !== (payload.category ?? '')) {
      next.category = category || null;
    }

    if ((note || '') !== (payload.note ?? '')) {
      next.note = note || null;
    }

    pickers.forEach(({ key }) => {
      if (wallets[key] && wallets[key] !== payload[key]) {
        next[key] = wallets[key];
      }
    });

    return next;
  }, [amount, category, note, wallets, payload, pickers]);

  const changed = Object.keys(patch).length > 0;

  const handleAmount = useCallback((event) => setAmount(digitsOf(event.target.value)), []);

  return (
    <Stack sx={{ gap: 2 }}>
      <Stack direction="row" sx={{ gap: 1, alignItems: 'center' }}>
        <Button
          onClick={onBack}
          disabled={saving}
          startIcon={<Iconify icon="lega:back" width={18} />}
          sx={{ ml: -1, minHeight: 44, fontWeight: 800, color: 'text.primary' }}
        >
          Balik
        </Button>
      </Stack>

      <Box>
        <FieldLabel htmlFor="revisi-jumlah">JUMLAH</FieldLabel>
        <Box
          sx={{
            mt: 0.75,
            px: 1.75,
            gap: 1,
            height: 64,
            display: 'flex',
            alignItems: 'center',
            borderRadius: 2.25,
            border: '2.5px solid',
            borderColor: 'primary.main',
          }}
        >
          <Box
            component="span"
            aria-hidden
            sx={{ fontSize: 20, fontWeight: 800, color: 'text.secondary' }}
          >
            Rp
          </Box>
          <InputBase
            id="revisi-jumlah"
            value={amount ? Number(amount).toLocaleString('id-ID') : ''}
            onChange={handleAmount}
            placeholder="0"
            inputProps={{ inputMode: 'numeric', 'aria-label': 'Jumlah' }}
            sx={{
              flex: '1 1 auto',
              minWidth: 0,
              '& .MuiInputBase-input': {
                p: 0,
                fontSize: 30,
                fontWeight: 800,
                letterSpacing: '-0.02em',
                fontVariantNumeric: 'tabular-nums',
              },
            }}
          />
        </Box>
        {Number(amount) !== payload.amount && (
          <Typography sx={{ mt: 0.75, fontSize: 12, fontWeight: 700, color: 'text.secondary' }}>
            Semula {Number(payload.amount ?? 0).toLocaleString('id-ID')}
          </Typography>
        )}
      </Box>

      {pickers.map(({ key, label }) => (
        <Box key={key}>
          <FieldLabel>{label.toUpperCase()}</FieldLabel>
          <Box sx={{ mt: 1 }}>
            <WalletPicker
              label={label}
              accounts={accounts}
              selectedId={wallets[key]}
              onSelect={(id) => setWallets((prev) => ({ ...prev, [key]: id }))}
            />
          </Box>
        </Box>
      ))}

      {card.kind !== 'transfer' && (
        <Box>
          <FieldLabel>KATEGORI</FieldLabel>
          <Stack direction="row" sx={{ mt: 1, gap: 1, overflowX: 'auto', pb: 0.5 }}>
            {categories.map((name) => (
              <ChoiceChip
                key={name}
                label={name}
                active={category === name}
                onClick={() => setCategory(category === name ? '' : name)}
              />
            ))}
          </Stack>
        </Box>
      )}

      <Box>
        <FieldLabel htmlFor="revisi-catatan">CATATAN</FieldLabel>
        <InputBase
          id="revisi-catatan"
          value={note}
          onChange={(event) => setNote(event.target.value)}
          placeholder="Opsional"
          inputProps={{ 'aria-label': 'Catatan' }}
          sx={{
            mt: 0.75,
            px: 1.75,
            width: 1,
            height: 48,
            borderRadius: 2,
            border: '1.5px solid',
            borderColor: 'grey.300',
            '& .MuiInputBase-input': { p: 0, fontSize: 16, fontWeight: 600 },
          }}
        />
      </Box>

      <Stack direction="row" sx={{ gap: 1.25, p: 1.5, borderRadius: 2, bgcolor: 'grey.100' }}>
        <Iconify
          width={18}
          icon="solar:info-circle-bold"
          sx={{ mt: 0.2, flexShrink: 0, color: 'text.secondary' }}
        />
        <Typography sx={{ fontSize: 13, lineHeight: '19px', fontWeight: 600, color: 'grey.700' }}>
          Perubahan bikin draft baru. Sampai lu geser konfirmasi, nggak ada yang masuk ke catatan.
        </Typography>
      </Stack>

      {error && (
        <Typography sx={{ fontSize: 13, fontWeight: 700, color: 'error.dark' }}>{error}</Typography>
      )}

      <Button
        fullWidth
        loading={saving}
        disabled={!changed}
        onClick={() => onApply(patch)}
        sx={{
          minHeight: 50,
          fontSize: 15,
          fontWeight: 800,
          borderRadius: 999,
          color: 'common.white',
          bgcolor: 'text.primary',
          '&:hover': { bgcolor: 'grey.700' },
          '&.Mui-disabled': { color: 'grey.500', bgcolor: 'grey.200' },
        }}
      >
        {changed ? 'Pakai perubahan' : 'Belum ada yang diubah'}
      </Button>
    </Stack>
  );
}

// ----------------------------------------------------------------------

function FieldLabel({ children, htmlFor }) {
  return (
    <Typography
      component="label"
      htmlFor={htmlFor}
      sx={{
        display: 'block',
        fontSize: 10,
        fontWeight: 800,
        letterSpacing: '0.07em',
        color: 'text.secondary',
      }}
    >
      {children}
    </Typography>
  );
}
