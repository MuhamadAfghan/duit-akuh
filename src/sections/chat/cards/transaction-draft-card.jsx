import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';

import { formatRupiah } from 'src/utils/format-money';

import { ActionCard } from './action-card';

// ----------------------------------------------------------------------

const TYPE_LABELS = {
  expense: 'Pengeluaran',
  income: 'Pemasukan',
  transfer: 'Transfer',
  topup: 'Top-up',
  withdrawal: 'Tarik tunai',
};

function DetailRow({ label, value }) {
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
 * Draft card for a proposed transaction (PRD FR04/FR05).
 *
 * Shows the fields the PRD requires a draft to carry, so the user can see
 * how their sentence was interpreted before anything is written: type,
 * amount, source/destination account, category, date, optional merchant and
 * note.
 *
 * `draft.amount` is integer rupiah. Nothing here derives a balance; the
 * `impact` rows arrive pre-computed.
 */
export function TransactionDraftCard({ draft, impact, status, statusMessage, ...other }) {
  const typeLabel = TYPE_LABELS[draft.type] ?? draft.type;

  return (
    <ActionCard
      title={`${typeLabel} ${formatRupiah(draft.amount)}`}
      caption={draft.interpretation}
      impact={impact}
      status={status}
      statusMessage={statusMessage}
      confirmLabel="Simpan"
      {...other}
    >
      <Stack spacing={1}>
        <DetailRow label="Jenis" value={typeLabel} />
        <DetailRow label="Nominal" value={formatRupiah(draft.amount)} />

        {draft.from && <DetailRow label="Dari" value={draft.from} />}
        {draft.to && <DetailRow label="Ke" value={draft.to} />}
        {draft.category && <DetailRow label="Kategori" value={draft.category} />}

        <DetailRow label="Tanggal" value={draft.date} />

        {draft.merchant && <DetailRow label="Merchant" value={draft.merchant} />}
        {draft.note && <DetailRow label="Catatan" value={draft.note} />}

        {/* Fees are a separate expense, never folded into the transfer
            amount (FR02/AC02) - so they get their own visible row. */}
        {!!draft.fee && <DetailRow label="Biaya admin" value={formatRupiah(draft.fee)} />}
      </Stack>
    </ActionCard>
  );
}
