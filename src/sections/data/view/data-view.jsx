'use client';

import { useState, useEffect, useCallback } from 'react';

import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';

import { paths } from 'src/routes/paths';

import { formatRupiahPlain } from 'src/utils/format-money';

import { accountsApi, transactionsApi } from 'src/lib/api';

import { Iconify } from 'src/components/iconify';

import {
  Money,
  ListRow,
  Loading,
  ListCard,
  BoardBody,
  RowAvatar,
  FilterChip,
  BoardTitle,
  RowDivider,
  SurfaceEmpty,
  SkeletonRows,
} from '../../common';

// ----------------------------------------------------------------------

/** Only the keywords the backend actually resolves (domain/periods.py). */
const PERIODS = [
  { value: 'bulan_ini', label: 'Bulan ini' },
  { value: 'minggu_ini', label: 'Minggu ini' },
  { value: 'bulan_lalu', label: 'Bulan lalu' },
  { value: '30_hari', label: '30 hari' },
  { value: 'tahun_ini', label: 'Tahun ini' },
  { value: 'semua', label: 'Semua waktu' },
];

const TYPE_FILTERS = [
  { value: null, label: 'Semua jenis' },
  { value: 'expense', label: 'Pengeluaran' },
  { value: 'income', label: 'Pemasukan' },
  { value: 'transfer', label: 'Pindah kantong' },
  { value: 'card_payment', label: 'Bayar kartu' },
  { value: 'refund', label: 'Refund' },
];

const TYPES = {
  opening: { label: 'Saldo awal', icon: 'lega:wallet', tone: 'grey', note: 'bukan pemasukan' },
  income: { label: 'Pemasukan', icon: 'lega:arrow-up', tone: 'green', sign: 1 },
  expense: { label: 'Pengeluaran', icon: 'lega:arrow-down', tone: 'red', sign: -1 },
  transfer: { label: 'Pindah', icon: 'lega:swap', tone: 'blue', note: 'bukan pengeluaran' },
  card_payment: {
    label: 'Bayar tagihan kartu',
    icon: 'lega:card',
    tone: 'grey',
    note: 'bukan pengeluaran baru',
  },
  refund: { label: 'Refund', icon: 'lega:arrow-up', tone: 'green', sign: 1 },
  reversal: { label: 'Dibalik', icon: 'solar:restart-bold', tone: 'grey' },
  // Both legs land on categories, so no wallet name appears beside it
  // and no sign is shown — nothing was spent or earned here.
  reclassify: {
    label: 'Pindah kategori',
    icon: 'solar:tag-horizontal-bold-duotone',
    tone: 'grey',
    note: 'saldo tidak berubah',
  },
};

/**
 * The headline figure.
 *
 * Deliberately the largest single leg rather than a sum: entries sum to
 * zero by construction, so "the amount" is a presentation choice. For a
 * transfer this shows what moved, and the fee stays its own row.
 */
function headline(entries) {
  if (!entries?.length) {
    return 0;
  }

  return entries.reduce((best, e) => (Math.abs(e.amount) > Math.abs(best) ? e.amount : best), 0);
}

/** Groups by calendar day in the browser's zone, newest first. */
function byDay(rows) {
  const groups = new Map();

  rows.forEach((row) => {
    const date = new Date(row.occurred_at);
    const key = date.toDateString();

    if (!groups.has(key)) {
      groups.set(key, { date, rows: [], out: 0, in: 0 });
    }

    const group = groups.get(key);
    group.rows.push(row);

    const type = TYPES[row.type];
    const amount = Math.abs(headline(row.entries));

    if (type?.sign === -1) {
      group.out += amount;
    }
    if (type?.sign === 1) {
      group.in += amount;
    }
  });

  return [...groups.values()];
}

function dayLabel(date) {
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);

  if (date.toDateString() === today.toDateString()) {
    return 'Hari ini';
  }
  if (date.toDateString() === yesterday.toDateString()) {
    return 'Kemarin';
  }

  return date.toLocaleDateString('id-ID', { day: 'numeric', month: 'short' });
}

// ----------------------------------------------------------------------

export function DataView() {
  const [transactions, setTransactions] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [names, setNames] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [period, setPeriod] = useState('bulan_ini');
  const [type, setType] = useState(null);
  const [accountId, setAccountId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [rows, wallets] = await Promise.all([
        transactionsApi.list({ limit: 100, period, type, accountId }),
        accountsApi.list(),
      ]);
      setTransactions(rows);
      setAccounts(wallets);
      setNames(Object.fromEntries(wallets.map((account) => [account.id, account.name])));
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [period, type, accountId]);

  useEffect(() => {
    load();
  }, [load]);

  const days = byDay(transactions);

  return (
    <>
      <BoardTitle
        title="Data"
        action={
          <Stack direction="row" sx={{ gap: 1, alignItems: 'center' }}>
            {transactions.length > 0 && (
              <Box
                component="a"
                /* A plain link, not fetch(): the browser handles the
                   download and the Content-Disposition filename, and the
                   session cookie rides along because it is same-origin. */
                href="/srv/export/transactions.csv?period=semua"
                sx={{
                  px: 1.75,
                  gap: 0.75,
                  height: 40,
                  fontSize: 13,
                  display: 'flex',
                  fontWeight: 800,
                  borderRadius: 999,
                  alignItems: 'center',
                  bgcolor: 'common.white',
                  color: 'text.primary',
                  textDecoration: 'none',
                }}
              >
                <Iconify icon="lega:download" width={16} />
                CSV
              </Box>
            )}
          </Stack>
        }
      />

      <Stack direction="row" sx={{ px: 2, pb: 1.5, gap: 1, overflowX: 'auto' }}>
        <FilterChip value={period} onChange={setPeriod} options={PERIODS} />
        <FilterChip
          value={accountId}
          onChange={setAccountId}
          options={[
            { value: null, label: 'Semua kantong' },
            ...accounts.map((account) => ({ value: account.id, label: account.name })),
          ]}
        />
        <FilterChip value={type} onChange={setType} options={TYPE_FILTERS} />
      </Stack>

      <BoardBody>
        {loading && (
          <Loading label="Memuat transaksi…">
            <SkeletonRows rows={6} />
          </Loading>
        )}
        {error && (
          <SurfaceEmpty icon="solar:danger-triangle-bold" title="Gagal memuat data" body={error} />
        )}

        {!error && !loading && transactions.length === 0 && (
          <SurfaceEmpty
            icon="lega:list"
            title="Belum ada transaksi"
            body="Catat lewat chat atau tombol tengah di bawah. Semuanya muncul di sini."
          />
        )}

        {!error &&
          days.map((day) => (
            <Box
              key={day.date.toISOString()}
              sx={{ gap: 1, display: 'flex', flexDirection: 'column' }}
            >
              <Stack
                direction="row"
                sx={{ px: 0.5, gap: 2, alignItems: 'baseline', justifyContent: 'space-between' }}
              >
                <Typography sx={{ fontSize: 13, fontWeight: 800 }}>{dayLabel(day.date)}</Typography>
                <Typography sx={{ fontSize: 12, fontWeight: 700, color: 'text.secondary' }}>
                  {day.out > 0 && `keluar ${formatRupiahPlain(day.out)}`}
                  {day.out > 0 && day.in > 0 && ' · '}
                  {day.in > 0 && `masuk ${formatRupiahPlain(day.in)}`}
                </Typography>
              </Stack>

              <ListCard>
                {day.rows.map((row, index) => (
                  <Box key={row.id}>
                    {index > 0 && <RowDivider />}
                    <Row row={row} names={names} />
                  </Box>
                ))}
              </ListCard>
            </Box>
          ))}

        {!error && transactions.length > 0 && (
          <Typography
            sx={{
              fontSize: 12,
              lineHeight: 1.5,
              fontWeight: 600,
              textAlign: 'center',
              color: 'text.secondary',
            }}
          >
            Ekspor ikut filter yang nyala. Satu baris per sisi, jadi transfer tetap utuh.
          </Typography>
        )}
      </BoardBody>
    </>
  );
}

// ----------------------------------------------------------------------

function Row({ row, names }) {
  const type = TYPES[row.type] ?? { label: row.type, icon: 'lega:list', tone: 'grey' };
  const amount = headline(row.entries);
  const reversed = row.type === 'reversal';

  const wallets = row.entries
    .map((entry) => names[entry.account_id])
    .filter(Boolean)
    .join(' → ');

  const title = row.merchant || row.description || type.label;
  const note = [wallets, type.note].filter(Boolean).join(' · ');

  return (
    <ListRow
      href={paths.chat}
      avatar={<RowAvatar tone={reversed ? 'grey' : type.tone} icon={type.icon} />}
      title={title}
      note={note}
      value={undefined}
      action={
        <Money
          amount={type.sign ? Math.abs(amount) * type.sign : Math.abs(amount)}
          signed={Boolean(type.sign)}
          sx={{
            fontSize: 16,
            fontWeight: 800,
            whiteSpace: 'nowrap',
            ...(reversed && { color: 'text.disabled', textDecoration: 'line-through' }),
            ...(type.sign === 1 && !reversed && { color: 'primary.dark' }),
            ...(!type.sign && !reversed && { color: 'text.secondary' }),
          }}
        />
      }
    />
  );
}
