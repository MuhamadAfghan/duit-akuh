import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Stack from '@mui/material/Stack';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';

import { formatRupiah } from 'src/utils/format-money';

import { Iconify } from 'src/components/iconify';

import { BatchBody } from './batch-card';
import { Pill, Money, BoardNote } from '../../common';
import { TwoSided, DetailRow, ActionCard, ImpactLine } from './action-card';

// ----------------------------------------------------------------------

const TYPE_KICKERS = {
  expense: 'PENGELUARAN',
  income: 'PEMASUKAN',
  transfer: 'PINDAH KANTONG',
  card_payment: 'BAYAR TAGIHAN KARTU',
  refund: 'REFUND',
};

const ACCOUNT_TYPE_LABELS = {
  bank: 'Rekening bank',
  ewallet: 'E-wallet',
  cash: 'Tunai',
  credit_card: 'Kartu kredit',
};

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

/**
 * Turns a draft into the card its kind deserves.
 *
 * Driven by `kind` rather than by assuming every draft is a
 * transaction: goals, wallets and reversals carry their amount under a
 * different key and once rendered as "Rp0".
 *
 * Each branch also carries the one sentence that stops the entry being
 * misread — a transfer is not spending, a card bill is not a second
 * expense, an opening balance is not income, a budget is not money set
 * aside. Those are the rules the ledger enforces, said where somebody
 * is about to act on them.
 */
export function describeDraft(card, names, options = {}) {
  const { payload = {}, kind } = card;
  const impact = card.impact ?? [];

  if (kind === 'batch') {
    const items = payload.items ?? [];
    const kinds = new Set(items.map((item) => item.type));
    const wallets = new Set(
      items.map((item) => names[item.from_account_id] ?? names[item.to_account_id]).filter(Boolean)
    );
    const blocked = items.filter((item) => (item.unresolved ?? []).length).length;

    return {
      kicker: `${items.length} ${kinds.size === 1 ? (TYPE_KICKERS[[...kinds][0]] ?? 'CATATAN') : 'CATATAN'}`,
      // Negative because a batch is only ever offered for things that
      // already happened, and every kind in it moves money out of or
      // into named wallets - the sum is what leaves the person's hands.
      amount: -(payload.items_total ?? 0),
      amountSigned: true,
      subtitle: wallets.size === 1 ? [...wallets][0] : `${wallets.size || 'Belum ada'} kantong`,
      confirmLabel: `Geser untuk simpan ${items.length} catatan`,
      // The server refuses an incomplete batch too; this only saves the
      // round trip and says which answer is missing.
      blockedReason: blocked
        ? `Pilih kantong ${blocked > 1 ? `${blocked} catatan` : 'catatannya'} dulu`
        : null,
      body: (
        <BatchBody
          payload={{ ...payload, impactRows: impact }}
          names={names}
          accounts={options.accounts ?? []}
          onPatchItem={options.onPatchItem}
        />
      ),
    };
  }

  if (kind === 'goal') {
    return {
      kicker: 'TARGET BARU',
      amount: payload.target_amount ?? 0,
      subtitle: payload.name,
      confirmLabel: 'Geser untuk bikin target',
      body: (
        <Stack sx={{ gap: 1 }}>
          <DetailRow
            label="Tenggat"
            value={payload.target_date ? payload.target_date.slice(0, 10) : 'Belum ditentukan'}
          />
          <DetailRow label="Prioritas" value={payload.priority} />
        </Stack>
      ),
    };
  }

  if (kind === 'allocation') {
    return {
      kicker: 'SISIHKAN KE TARGET',
      amount: payload.amount ?? 0,
      subtitle: names[payload.account_id],
      confirmLabel: 'Geser untuk sisihkan',
      body: (
        <Stack sx={{ gap: 1.5 }}>
          <Impacts impact={impact} />
          <BoardNote>
            Uangnya cuma ditandai supaya nggak kepakai. Saldo kantongnya tetap, dan total aset lu
            nggak naik, nggak turun.
          </BoardNote>
        </Stack>
      ),
    };
  }

  if (kind === 'budget') {
    const previous = payload.previous_amount ?? payload.current_amount;

    return {
      kicker: `BUDGET · ${(payload.category ?? '').toUpperCase()}`,
      amount: payload.amount ?? 0,
      subtitle: 'Per bulan',
      confirmLabel: 'Geser untuk atur budget',
      body: (
        <Stack sx={{ gap: 1.5 }}>
          {Number.isInteger(previous) && (
            <DetailRow label="Limit sekarang" value={formatRupiah(previous)} />
          )}
          <BoardNote>
            Budget itu rencana, bukan uang. Angka <strong>bebas pakai</strong> lu nggak berubah
            karena ini.
          </BoardNote>
        </Stack>
      ),
    };
  }

  if (kind === 'account') {
    return {
      kicker: 'KANTONG BARU',
      amount: payload.opening_balance ?? 0,
      subtitle: `${payload.name} · ${ACCOUNT_TYPE_LABELS[payload.type] ?? payload.type}`,
      confirmLabel: 'Geser untuk simpan kantong',
      body: (
        <Stack sx={{ gap: 1.5 }}>
          {payload.credit_limit != null && (
            <DetailRow label="Limit kartu" value={formatRupiah(payload.credit_limit)} />
          )}
          <BoardNote>
            Saldo awal <strong>bukan pemasukan</strong>. Ini titik mulai, jadi laporan bulan ini
            nggak kelihatan seperti lu baru dapat uang sebanyak itu.
          </BoardNote>
        </Stack>
      ),
    };
  }

  if (kind === 'reversal') {
    return {
      kicker: 'BATALKAN TRANSAKSI',
      amount: payload.amount ?? null,
      tone: 'bad',
      subtitle: payload.description ?? payload.summary,
      destructive: true,
      confirmLabel: 'Batalkan',
      body: (
        <BoardNote tone="bad">
          Catatan lama tetap ada, ditambah catatan pembalik. Riwayatnya bisa ditelusuri, dan nggak
          ada yang hilang diam-diam.
        </BoardNote>
      ),
    };
  }

  // A transaction. The type lives on the payload here, not on `kind`.
  const type = payload.type ?? kind;
  const amount = payload.amount ?? 0;

  if (type === 'transfer') {
    return {
      kicker: payload.fee ? 'PINDAH KANTONG + ADMIN' : 'PINDAH KANTONG',
      amount: null,
      confirmLabel: 'Geser untuk simpan',
      body: (
        <Stack sx={{ gap: 1.5 }}>
          <TwoSided
            from={{ name: names[payload.from_account_id], amount }}
            to={{ name: names[payload.to_account_id], amount }}
          />

          {payload.fee > 0 && (
            <DetailRow label="Biaya admin (pengeluaran)" value={formatRupiah(payload.fee)} />
          )}

          <BoardNote tone="info">
            Total uang lu <strong>tidak berubah</strong>. Ini pindah tempat, jadi nggak masuk
            laporan pengeluaran
            {payload.fee > 0 ? ' — cuma biaya adminnya yang dihitung.' : '.'}
          </BoardNote>
        </Stack>
      ),
    };
  }

  if (type === 'card_payment') {
    return {
      kicker: 'BAYAR TAGIHAN KARTU',
      amount,
      confirmLabel: 'Geser untuk simpan',
      body: (
        <Stack sx={{ gap: 1.5 }}>
          <Impacts impact={impact} />
          <BoardNote tone="warn">
            Belanjanya sudah dihitung waktu digesek. Pembayaran ini <strong>bukan</strong>{' '}
            pengeluaran baru.
          </BoardNote>
        </Stack>
      ),
    };
  }

  const incoming = type === 'income' || type === 'refund';
  const card_ = names[payload.from_account_id];

  return {
    kicker: [TYPE_KICKERS[type] ?? type, payload.category?.toUpperCase()]
      .filter(Boolean)
      .join(' · '),
    amount: incoming ? amount : -amount,
    amountSigned: true,
    tone: incoming ? 'good' : 'neutral',
    subtitle: [card_ ?? names[payload.to_account_id], payload.merchant].filter(Boolean).join(' · '),
    confirmLabel: 'Geser untuk simpan',
    body: (
      <Stack sx={{ gap: 1.5 }}>
        <Impacts impact={impact} />
        <Stack sx={{ gap: 1 }}>
          <DetailRow
            label="Tanggal"
            value={payload.occurred_at ? payload.occurred_at.slice(0, 10) : 'Hari ini'}
          />
          <DetailRow label="Catatan" value={payload.note} />
        </Stack>
      </Stack>
    ),
  };
}

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

// ----------------------------------------------------------------------

/**
 * The card in the thread.
 *
 * A *pending* draft is not decided here any more — it opens in a sheet
 * (`DraftSheet`), which is the only surface big enough to show the
 * figures, the impact and an editor without the keyboard pushing the
 * confirmation off screen. What stays in the thread is a stub, so a
 * dismissed sheet leaves a way back in rather than a draft you can
 * only reach by scrolling and guessing.
 *
 * A *settled* draft is the full receipt, exactly as before: that is
 * the record of what happened, and it belongs in the history.
 */
export function DraftCard({
  card,
  names = {},
  accounts = [],
  sheet = false,
  onOpen,
  onConfirm,
  onCancel,
  onRevise,
  onPatchItem,
}) {
  const described = describeDraft(card, names, { accounts, onPatchItem });

  // `sheet` is the same card rendered inside DraftSheet, where it is
  // the whole point of the surface rather than a line in a history.
  if (card.status === 'pending' && !sheet) {
    return <PendingStub described={described} onOpen={onOpen} />;
  }

  return (
    <ActionCard
      kicker={described.kicker}
      amount={described.amount}
      amountSigned={described.amountSigned}
      subtitle={described.subtitle}
      tone={described.tone}
      destructive={described.destructive}
      confirmLabel={described.confirmLabel}
      blockedReason={described.blockedReason}
      status={CARD_STATUS[card.status] ?? 'draft'}
      statusMessage={SETTLED_MESSAGES[card.status]}
      onConfirm={onConfirm}
      onRevise={onRevise}
      onCancel={onCancel}
    >
      <Box sx={{ pb: 0.5 }}>{described.body}</Box>
    </ActionCard>
  );
}

// ----------------------------------------------------------------------

function PendingStub({ described, onOpen }) {
  return (
    <Card sx={{ width: 1, borderRadius: 3, overflow: 'hidden' }}>
      <Box sx={{ px: 2.25, py: 2 }}>
        <Stack direction="row" sx={{ gap: 1, alignItems: 'center' }}>
          <Typography
            noWrap
            sx={{
              flexGrow: 1,
              minWidth: 0,
              fontSize: 11,
              fontWeight: 800,
              letterSpacing: '0.06em',
              color: 'text.secondary',
            }}
          >
            {described.kicker}
          </Typography>

          <Pill>BELUM TERSIMPAN</Pill>
        </Stack>

        {described.amount != null && (
          <Money
            amount={described.amount}
            signed={described.amountSigned}
            sx={{ mt: 1, fontSize: 28, lineHeight: '32px', fontWeight: 800 }}
          />
        )}

        {described.subtitle && (
          <Typography sx={{ mt: 0.5, fontSize: 14, fontWeight: 600, color: 'text.secondary' }}>
            {described.subtitle}
          </Typography>
        )}

        <Button
          fullWidth
          onClick={onOpen}
          endIcon={<Iconify icon="lega:arrow-right" width={18} />}
          sx={{
            mt: 2,
            minHeight: 48,
            fontSize: 15,
            fontWeight: 800,
            borderRadius: 999,
            color: 'common.white',
            bgcolor: 'text.primary',
            '&:hover': { bgcolor: 'grey.700' },
          }}
        >
          Cek &amp; konfirmasi
        </Button>
      </Box>
    </Card>
  );
}
