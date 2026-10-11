import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';

import { formatRupiahPlain } from 'src/utils/format-money';

import { Iconify } from 'src/components/iconify';

import { ImpactLine } from './action-card';

// ----------------------------------------------------------------------

/** Which account slot each kind actually uses, for the picker's label. */
const SLOT_LABELS = {
  from_account_id: 'Dari kantong mana?',
  to_account_id: 'Masuk ke kantong mana?',
  card_account_id: 'Kartu yang mana?',
};

const TYPE_WORDS = {
  expense: 'PENGELUARAN',
  income: 'PEMASUKAN',
  transfer: 'PINDAH KANTONG',
  card_payment: 'BAYAR KARTU',
  refund: 'REFUND',
};

// ----------------------------------------------------------------------

/**
 * Several entries from one sentence, as one card.
 *
 * The strip at the top is the whole reason this is not three cards: it
 * is where the app shows that it understood "150rb" as a *total* and
 * not as a fourth thing to record. Without it there is no way for the
 * person to tell the difference between a correct batch and one that
 * doubled their spending.
 *
 * An entry whose wallet nobody has chosen is drawn amber with the
 * wallets right under it, rather than being quietly assigned one. The
 * confirmation stays locked until the last of them is answered — and
 * the server refuses it too, so this is a convenience, not the rule.
 */
export function BatchBody({ payload, names, accounts, onPatchItem }) {
  const items = payload.items ?? [];

  return (
    <Stack sx={{ gap: 1.5 }}>
      <Reconciliation payload={payload} />

      <Stack sx={{ gap: 1 }}>
        {items.map((item, index) => (
          <ItemRow
            // Position is the identity here: it is what the server's
            // patch addresses, and entries are never reordered.
            key={`${item.type}-${index}`}
            item={item}
            names={names}
            accounts={accounts}
            onPick={
              onPatchItem
                ? (field, accountId) => onPatchItem(index, { [field]: accountId })
                : undefined
            }
          />
        ))}
      </Stack>

      <Impacts impact={payload.impactRows ?? []} />
    </Stack>
  );
}

// ----------------------------------------------------------------------

function Reconciliation({ payload }) {
  const parts = (payload.items ?? []).map((item) => formatRupiahPlain(item.amount ?? 0));
  const total = formatRupiahPlain(payload.items_total ?? 0);

  if (payload.stated_total == null) {
    return null;
  }

  if (payload.matches) {
    return (
      <Stack
        direction="row"
        sx={{ gap: 1.25, p: 1.5, borderRadius: 2, bgcolor: 'primary.lighter' }}
      >
        <Iconify
          width={18}
          icon="solar:check-circle-bold"
          sx={{ mt: 0.1, flexShrink: 0, color: 'primary.main' }}
        />
        <Box sx={{ minWidth: 0 }}>
          <Typography
            sx={{
              fontSize: 13,
              fontWeight: 800,
              color: 'primary.darker',
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {parts.join(' + ')} = {total} — cocok
          </Typography>
          <Typography sx={{ mt: 0.25, fontSize: 12, fontWeight: 600, color: 'primary.dark' }}>
            Angka {formatRupiahPlain(payload.stated_total)} itu totalnya, bukan catatan tambahan.
          </Typography>
        </Box>
      </Stack>
    );
  }

  const short = (payload.difference ?? 0) > 0;

  return (
    <Stack direction="row" sx={{ gap: 1.25, p: 1.5, borderRadius: 2, bgcolor: '#FFF5CC' }}>
      <Iconify
        width={18}
        icon="solar:danger-triangle-bold"
        sx={{ mt: 0.1, flexShrink: 0, color: '#B76E00' }}
      />
      <Box sx={{ minWidth: 0 }}>
        <Typography sx={{ fontSize: 13, fontWeight: 800, color: '#7A4100' }}>
          Lu bilang {formatRupiahPlain(payload.stated_total)}, rinciannya {total} — beda{' '}
          {formatRupiahPlain(Math.abs(payload.difference ?? 0))}.
        </Typography>
        <Typography sx={{ mt: 0.25, fontSize: 12, fontWeight: 600, color: '#7A4100' }}>
          {short
            ? 'Yang kesimpan cuma rinciannya. Selisihnya nggak dicatat — tambahin sendiri kalau perlu.'
            : 'Rinciannya lebih besar dari total yang lu sebut. Cek lagi angkanya.'}
        </Typography>
      </Box>
    </Stack>
  );
}

// ----------------------------------------------------------------------

function ItemRow({ item, names, accounts, onPick }) {
  const blocked = (item.unresolved ?? []).length > 0;
  const field = item.unresolved?.[0];

  const wallet =
    names[item.from_account_id] ?? names[item.to_account_id] ?? names[item.card_account_id];

  return (
    <Box
      sx={{
        borderRadius: 2,
        border: '1.5px solid',
        borderColor: blocked ? '#B76E00' : 'grey.200',
        bgcolor: blocked ? '#FFF5CC' : 'transparent',
      }}
    >
      <Stack direction="row" sx={{ px: 1.5, py: 1.25, gap: 1, alignItems: 'center' }}>
        <Box sx={{ flex: '1 1 auto', minWidth: 0 }}>
          <Typography
            noWrap
            sx={{ fontSize: 15, fontWeight: 800, color: blocked ? '#7A4100' : 'text.primary' }}
          >
            {item.category ?? item.merchant ?? TYPE_WORDS[item.type] ?? item.type}
          </Typography>

          <Typography
            noWrap
            sx={{
              mt: 0.125,
              fontSize: 12,
              fontWeight: 700,
              color: blocked ? '#7A4100' : 'text.secondary',
            }}
          >
            {blocked ? (SLOT_LABELS[field] ?? 'Kantongnya belum jelas') : (wallet ?? '—')}
          </Typography>
        </Box>

        <Typography
          sx={{
            flexShrink: 0,
            fontSize: 15,
            fontWeight: 800,
            fontVariantNumeric: 'tabular-nums',
            color: blocked ? '#7A4100' : 'text.primary',
          }}
        >
          {formatRupiahPlain(item.amount ?? 0)}
        </Typography>
      </Stack>

      {blocked && onPick && (
        <Stack
          direction="row"
          role="group"
          aria-label={SLOT_LABELS[field] ?? 'Pilih kantong'}
          sx={{ px: 1.5, pb: 1.25, gap: 0.875, overflowX: 'auto' }}
        >
          {accounts.map((account) => (
            <Box
              key={account.id}
              component="button"
              type="button"
              onClick={() => onPick(field, account.id)}
              sx={{
                px: 1.75,
                height: 40,
                flexShrink: 0,
                fontSize: 14,
                fontWeight: 800,
                cursor: 'pointer',
                borderRadius: 999,
                border: '1.5px solid #B76E00',
                color: '#7A4100',
                bgcolor: 'common.white',
              }}
            >
              {account.name}
            </Box>
          ))}
        </Stack>
      )}
    </Box>
  );
}

// ----------------------------------------------------------------------

function Impacts({ impact }) {
  if (!impact.length) {
    return null;
  }

  return (
    <Stack sx={{ gap: 0.75 }}>
      {impact.map((row) => (
        <ImpactLine key={row.account} label={row.account} before={row.before} after={row.after} />
      ))}
    </Stack>
  );
}
