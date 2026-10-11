import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';

import { formatRupiah } from 'src/utils/format-money';

import { ActionCard } from './action-card';

// ----------------------------------------------------------------------

const TRANSACTION_LABELS = {
  expense: 'Pengeluaran',
  income: 'Pemasukan',
  transfer: 'Transfer',
  card_payment: 'Bayar kartu',
  refund: 'Refund',
};

const ACCOUNT_TYPE_LABELS = {
  bank: 'Bank',
  ewallet: 'E-wallet',
  cash: 'Cash',
  credit_card: 'Kartu kredit',
};

function Row({ label, value }) {
  if (value == null || value === '') {
    return null;
  }

  return (
    <Stack direction="row" sx={{ justifyContent: 'space-between', gap: 2 }}>
      <Typography variant="body2" sx={{ color: 'text.secondary', flexShrink: 0 }}>
        {label}
      </Typography>
      <Typography variant="body2" sx={{ textAlign: 'right', fontWeight: 'fontWeightMedium' }}>
        {value}
      </Typography>
    </Stack>
  );
}

// ----------------------------------------------------------------------

/**
 * Describe a draft for the card: a title, a one-line caption, and rows.
 *
 * Driven by `kind` rather than by assuming every draft is a transaction.
 * It was: goals, new wallets and reversals all carry their amount under
 * a different key, so they rendered as "Rp0".
 *
 * `names` maps account ids to names, since payloads identify accounts
 * by id.
 */
function describe(card, names) {
  const { payload = {}, kind } = card;

  if (kind === 'goal') {
    return {
      title: `Target baru: ${payload.name}`,
      caption: `Sasaran ${formatRupiah(payload.target_amount ?? 0)}`,
      rows: [
        { label: 'Nama', value: payload.name },
        { label: 'Target', value: formatRupiah(payload.target_amount ?? 0) },
        {
          label: 'Tenggat',
          value: payload.target_date ? payload.target_date.slice(0, 10) : null,
        },
        { label: 'Prioritas', value: payload.priority ? String(payload.priority) : null },
      ],
    };
  }

  if (kind === 'allocation') {
    return {
      title: `Alokasi ${formatRupiah(payload.amount ?? 0)}`,
      caption: 'Menandai saldo yang sudah ada — tidak memindahkan uang.',
      rows: [
        { label: 'Target', value: payload.goal_name },
        { label: 'Dari kantong', value: payload.account_name ?? names[payload.account_id] },
        { label: 'Jumlah', value: formatRupiah(payload.amount ?? 0) },
      ],
    };
  }

  if (kind === 'budget') {
    return {
      title: `Budget ${payload.category}`,
      caption: 'Batas rencana belanja per bulan — bukan saldo.',
      rows: [
        { label: 'Kategori', value: payload.category },
        { label: 'Batas per bulan', value: formatRupiah(payload.amount ?? 0) },
      ],
    };
  }

  if (kind === 'account') {
    return {
      title: `Kantong baru: ${payload.name}`,
      caption: null,
      rows: [
        { label: 'Jenis', value: ACCOUNT_TYPE_LABELS[payload.type] ?? payload.type },
        {
          label: 'Saldo awal',
          value: payload.opening_balance ? formatRupiah(payload.opening_balance) : null,
        },
        {
          label: 'Limit kredit',
          value: payload.credit_limit ? formatRupiah(payload.credit_limit) : null,
        },
      ],
    };
  }

  if (kind === 'reversal') {
    return {
      title: 'Batalkan transaksi',
      caption: 'Transaksi aslinya tetap tersimpan; pembatalan dicatat terpisah.',
      rows: [],
    };
  }

  // A transaction. The type lives on the payload here, not on `kind`.
  const type = payload.type ?? kind;

  return {
    title: `${TRANSACTION_LABELS[type] ?? type} ${formatRupiah(payload.amount ?? 0)}`,
    caption: null,
    rows: [
      { label: 'Jenis', value: TRANSACTION_LABELS[type] ?? type },
      { label: 'Nominal', value: formatRupiah(payload.amount ?? 0) },
      { label: 'Dari', value: names[payload.from_account_id] },
      {
        label: 'Ke',
        value: names[payload.to_account_id] ?? names[payload.card_account_id],
      },
      { label: 'Kategori', value: payload.category },
      {
        label: 'Tanggal',
        value: payload.occurred_at ? payload.occurred_at.slice(0, 10) : 'Hari ini',
      },
      { label: 'Merchant', value: payload.merchant },
      { label: 'Catatan', value: payload.note },
      // Fees are a separate expense, never folded into the amount
      // (FR02/AC02), so they get their own row.
      { label: 'Biaya admin', value: payload.fee ? formatRupiah(payload.fee) : null },
    ],
  };
}

/** Backend draft statuses, mapped to what ActionCard renders. */
const CARD_STATUS = {
  pending: 'draft',
  confirmed: 'saved',
  cancelled: 'cancelled',
  stale: 'error',
  // Set locally while a confirmation is in flight.
  saving: 'saving',
};

const SETTLED_MESSAGES = {
  confirmed: 'Tersimpan.',
  cancelled: 'Draft dibatalkan. Tidak ada yang tersimpan.',
  stale: 'Draft sudah tidak berlaku karena datanya berubah. Coba ulangi.',
};

// ----------------------------------------------------------------------

export function DraftCard({ card, names = {}, onConfirm, onCancel }) {
  const { title, caption, rows } = describe(card, names);

  return (
    <ActionCard
      title={title}
      caption={caption}
      impact={(card.impact ?? []).map((row) => ({
        label: row.account,
        before: row.before,
        after: row.after,
      }))}
      status={CARD_STATUS[card.status] ?? 'draft'}
      statusMessage={SETTLED_MESSAGES[card.status]}
      confirmLabel="Geser untuk simpan"
      onConfirm={onConfirm}
      onCancel={onCancel}
    >
      <Stack spacing={1}>
        {rows.map((row) => (
          <Row key={row.label} label={row.label} value={row.value} />
        ))}
      </Stack>
    </ActionCard>
  );
}
