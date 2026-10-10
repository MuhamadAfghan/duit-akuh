'use client';

import { varAlpha } from 'minimal-shared/utils';
import { useState, useEffect, useCallback } from 'react';

import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Stack from '@mui/material/Stack';
import Divider from '@mui/material/Divider';
import Typography from '@mui/material/Typography';
import LinearProgress from '@mui/material/LinearProgress';

import { formatRupiah } from 'src/utils/format-money';

import { reportsApi, accountsApi } from 'src/lib/api';

import { Iconify } from 'src/components/iconify';

import { SurfaceEmpty, SurfaceHeader } from '../../common';

// ----------------------------------------------------------------------

function Figure({ label, value, hint, emphasis = false, negative = false }) {
  return (
    <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'baseline', gap: 2 }}>
      <Box>
        <Typography variant={emphasis ? 'subtitle1' : 'body2'} sx={{ color: 'text.secondary' }}>
          {label}
        </Typography>
        {hint && (
          <Typography variant="caption" sx={{ color: 'text.disabled' }}>
            {hint}
          </Typography>
        )}
      </Box>

      <Typography
        variant={emphasis ? 'h6' : 'subtitle2'}
        sx={{ color: negative ? 'error.main' : 'text.primary', whiteSpace: 'nowrap' }}
      >
        {formatRupiah(value)}
      </Typography>
    </Stack>
  );
}

// ----------------------------------------------------------------------

export function SummaryView() {
  const [data, setData] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [summary, rows, spending] = await Promise.all([
        accountsApi.summary(),
        accountsApi.list(),
        reportsApi.spending('bulan_ini'),
      ]);
      setData(summary);
      setAccounts(rows);
      setReport(spending);
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

    if (!accounts.length) {
      return (
        <SurfaceEmpty
          icon="solar:wad-of-money-bold"
          title="Belum ada kantong"
          body="Buat kantong pertamamu lewat chat, misalnya: “tambah BCA saldo 5 juta”."
        />
      );
    }

    return (
      <Stack sx={{ p: 2, gap: 2 }}>
        <Card sx={{ p: 2 }}>
          <Stack spacing={1.5}>
            <Figure label="Saldo likuid" value={data.liquid} emphasis />
            <Divider sx={{ borderStyle: 'dashed' }} />
            <Figure
              label="Uang bebas pakai"
              hint="Setelah alokasi target dan cadangan"
              value={data.free_to_spend}
              negative={data.is_shortfall}
            />
            <Figure label="Dana target" value={data.allocated} />
            <Figure label="Total utang" value={data.total_debt} negative={data.total_debt > 0} />
            <Divider sx={{ borderStyle: 'dashed' }} />
            <Figure label="Aset bersih" value={data.net_worth} />
          </Stack>

          {data.is_shortfall && (
            <Typography variant="caption" sx={{ mt: 1.5, display: 'block', color: 'error.main' }}>
              Alokasi dan cadangan melebihi saldo likuid.
            </Typography>
          )}
        </Card>

        <Card sx={{ p: 2 }}>
          <Typography variant="overline" sx={{ color: 'text.secondary' }}>
            Kantong
          </Typography>

          <Stack sx={{ mt: 1.5, gap: 1.5 }}>
            {accounts.map((account) => (
              <Stack
                key={account.id}
                direction="row"
                sx={{ justifyContent: 'space-between', alignItems: 'center', gap: 2 }}
              >
                <Stack direction="row" sx={{ alignItems: 'center', gap: 1.5, minWidth: 0 }}>
                  <Box
                    sx={(theme) => ({
                      width: 36,
                      height: 36,
                      flexShrink: 0,
                      display: 'grid',
                      placeItems: 'center',
                      borderRadius: '50%',
                      color: 'primary.main',
                      bgcolor: varAlpha(theme.vars.palette.primary.mainChannel, 0.12),
                    })}
                  >
                    <Iconify icon="solar:wad-of-money-bold" width={18} />
                  </Box>

                  <Box sx={{ minWidth: 0 }}>
                    <Typography variant="subtitle2" noWrap>
                      {account.name}
                    </Typography>
                    <Typography variant="caption" sx={{ color: 'text.disabled' }}>
                      {account.type}
                      {account.is_archived ? ' · diarsipkan' : ''}
                    </Typography>
                  </Box>
                </Stack>

                <Typography
                  variant="subtitle2"
                  sx={{
                    whiteSpace: 'nowrap',
                    color: account.debt > 0 ? 'error.main' : 'text.primary',
                  }}
                >
                  {account.debt > 0 ? formatRupiah(account.debt) : formatRupiah(account.balance)}
                </Typography>
              </Stack>
            ))}
          </Stack>
        </Card>

        {report && (
          <Card sx={{ p: 2 }}>
            {/* The period comes from the backend, which resolves it in the
                user's timezone — the label and the figures cannot disagree. */}
            <Typography variant="overline" sx={{ color: 'text.secondary' }}>
              {report.label}
            </Typography>

            <Stack sx={{ mt: 1.5, gap: 1 }}>
              <Figure label="Pengeluaran" value={report.expense_total} />
              <Figure label="Pemasukan" value={report.income_total} />
            </Stack>

            {report.categories.length > 0 && (
              <>
                <Divider sx={{ my: 2, borderStyle: 'dashed' }} />
                <Stack sx={{ gap: 1 }}>
                  {report.categories.map((category) => (
                    <Figure key={category.name} label={category.name} value={category.amount} />
                  ))}
                </Stack>
              </>
            )}

            {!report.transaction_count && (
              <Typography variant="caption" sx={{ color: 'text.disabled' }}>
                Belum ada transaksi pada periode ini.
              </Typography>
            )}
          </Card>
        )}
      </Stack>
    );
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', flex: '1 1 auto', minHeight: 0 }}>
      <SurfaceHeader title="Ringkasan" />
      <Box sx={{ flex: '1 1 auto', minHeight: 0, overflowY: 'auto' }}>{renderBody()}</Box>
    </Box>
  );
}
