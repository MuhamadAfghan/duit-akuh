'use client';

import { varAlpha } from 'minimal-shared/utils';
import { useState, useEffect, useCallback } from 'react';

import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import LinearProgress from '@mui/material/LinearProgress';

import { formatRupiah } from 'src/utils/format-money';

import { accountsApi, transactionsApi } from 'src/lib/api';

import { Label } from 'src/components/label';

import { SurfaceEmpty, SurfaceHeader } from '../../common';

// ----------------------------------------------------------------------

const TYPE_LABELS = {
  opening: 'Saldo awal',
  income: 'Pemasukan',
  expense: 'Pengeluaran',
  transfer: 'Transfer',
  card_payment: 'Bayar kartu',
  refund: 'Refund',
  reversal: 'Pembatalan',
};

/**
 * A transaction's headline amount.
 *
 * Deliberately the largest single leg rather than a sum: entries sum to
 * zero by construction, so "the amount" is a presentation choice. For a
 * transfer this shows what moved, with the fee visible as its own row
 * elsewhere.
 */
function headlineAmount(entries) {
  if (!entries?.length) {
    return 0;
  }

  return entries.reduce((best, e) => (Math.abs(e.amount) > Math.abs(best) ? e.amount : best), 0);
}

// ----------------------------------------------------------------------

export function DataView() {
  const [transactions, setTransactions] = useState([]);
  const [names, setNames] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [rows, accounts] = await Promise.all([transactionsApi.list(100), accountsApi.list()]);
      setTransactions(rows);
      setNames(Object.fromEntries(accounts.map((a) => [a.id, a.name])));
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const renderBody = () => {
    if (loading) {
      return <LinearProgress sx={{ m: 2 }} />;
    }

    if (error) {
      return <SurfaceEmpty icon="solar:danger-triangle-bold" title="Gagal memuat" body={error} />;
    }

    if (!transactions.length) {
      return (
        <SurfaceEmpty
          icon="solar:bill-list-bold"
          title="Belum ada transaksi"
          body="Catat yang pertama lewat chat, misalnya: “kemarin makan 35rb pakai BCA”."
        />
      );
    }

    return (
      <Stack sx={{ p: 2, gap: 1.5 }}>
        {transactions.map((tx) => {
          const amount = headlineAmount(tx.entries);
          const accounts = tx.entries
            .map((e) => names[e.account_id])
            .filter(Boolean)
            .join(' → ');

          return (
            /* Cards, not a table: FR17 requires wide tables to become
               stacked detail on a phone. */
            <Card key={tx.id} sx={{ p: 2 }}>
              <Stack
                direction="row"
                sx={{ justifyContent: 'space-between', alignItems: 'flex-start', gap: 2 }}
              >
                <Box sx={{ minWidth: 0 }}>
                  <Stack direction="row" sx={{ gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
                    <Typography variant="subtitle2">{TYPE_LABELS[tx.type] ?? tx.type}</Typography>
                    {tx.type === 'reversal' && (
                      <Label color="warning" variant="soft">
                        pembatalan
                      </Label>
                    )}
                  </Stack>

                  <Typography variant="caption" sx={{ color: 'text.disabled', display: 'block' }}>
                    {new Date(tx.occurred_at).toLocaleDateString('id-ID', {
                      day: 'numeric',
                      month: 'short',
                      year: 'numeric',
                    })}
                  </Typography>

                  {accounts && (
                    <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                      {accounts}
                    </Typography>
                  )}

                  {(tx.merchant || tx.note || tx.description) && (
                    <Typography variant="body2" sx={{ mt: 0.5 }}>
                      {tx.merchant || tx.note || tx.description}
                    </Typography>
                  )}
                </Box>

                <Typography
                  variant="subtitle2"
                  sx={(theme) => ({
                    whiteSpace: 'nowrap',
                    color:
                      amount < 0 ? theme.vars.palette.error.main : theme.vars.palette.success.main,
                  })}
                >
                  {formatRupiah(amount, { signed: true })}
                </Typography>
              </Stack>
            </Card>
          );
        })}
      </Stack>
    );
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', flex: '1 1 auto', minHeight: 0 }}>
      <SurfaceHeader
        title="Data"
        action={
          <Typography variant="caption" sx={{ color: 'text.disabled' }}>
            {transactions.length ? `${transactions.length} transaksi` : ''}
          </Typography>
        }
      />
      <Box
        sx={(theme) => ({
          flex: '1 1 auto',
          minHeight: 0,
          overflowY: 'auto',
          bgcolor: varAlpha(theme.vars.palette.grey['500Channel'], 0.04),
        })}
      >
        {renderBody()}
      </Box>
    </Box>
  );
}
