'use client';

import { useState, useEffect, useCallback } from 'react';

import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Stack from '@mui/material/Stack';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';
import IconButton from '@mui/material/IconButton';
import LinearProgress from '@mui/material/LinearProgress';

import { paths } from 'src/routes/paths';
import { RouterLink } from 'src/routes/components';

import { formatRupiah } from 'src/utils/format-money';

import { budgetsApi } from 'src/lib/api';

import { Iconify } from 'src/components/iconify';

import { BudgetForm } from '../budget-form';
import { SurfaceEmpty, SurfaceHeader } from '../../common';

// ----------------------------------------------------------------------

/**
 * Three states, and each one is told in words as well as colour.
 * Colour alone fails for anyone who cannot separate these hues, which
 * the PRD rules out (section 12).
 */
const STATES = {
  ok: { label: null, colour: 'primary', tint: null },
  approaching: { label: 'TIPIS', colour: 'warning', tint: 'warning.lighter' },
  exceeded: { label: 'LEWAT', colour: 'error', tint: 'error.lighter' },
};

export function BudgetView() {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setReport(await budgetsApi.list('bulan_ini'));
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

  const onRemove = async (category) => {
    try {
      await budgetsApi.remove(category);
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  const rows = report?.budgets ?? [];
  const usedPercent = report?.total_limit
    ? Math.min((report.total_spent / report.total_limit) * 100, 100)
    : 0;

  return (
    <>
      <SurfaceHeader
        title="Budget"
        backHref={paths.ringkasan}
        action={
          <IconButton
            aria-label="Atur budget"
            onClick={() => setEditing({ category: '', amount: '' })}
            sx={{ width: 44, height: 44, color: 'text.primary' }}
          >
            <Iconify icon="mingcute:add-line" width={22} />
          </IconButton>
        }
      />

      {loading && <LinearProgress />}

      <Box sx={{ flex: '1 1 auto', minHeight: 0, overflowY: 'auto', px: 2, pb: 3 }}>
        {error && (
          <SurfaceEmpty
            icon="solar:danger-triangle-bold"
            title="Gagal memuat budget"
            body={error}
          />
        )}

        {!error && !loading && rows.length === 0 && (
          <SurfaceEmpty
            icon="solar:chart-square-outline"
            title="Belum ada budget"
            body="Atur lewat tombol di atas, atau ketik di chat: “budget makan 2 juta per bulan”."
          />
        )}

        {!error && rows.length > 0 && (
          <Stack sx={{ gap: 2, pt: 1 }}>
            <Card variant="outlined" sx={{ p: 2, borderRadius: 2.5 }}>
              <Stack
                direction="row"
                sx={{ alignItems: 'flex-end', justifyContent: 'space-between' }}
              >
                <Box>
                  <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                    Kepakai {report.label}
                  </Typography>
                  <Typography variant="h4" sx={{ fontVariantNumeric: 'tabular-nums' }}>
                    {formatRupiah(report.total_spent)}
                  </Typography>
                </Box>
                <Typography variant="body2" sx={{ pb: 0.5, color: 'text.secondary' }}>
                  / {formatRupiah(report.total_limit)}
                </Typography>
              </Stack>

              <LinearProgress
                variant="determinate"
                value={usedPercent}
                sx={{ mt: 1.5, height: 12, borderRadius: 999 }}
              />

              <Typography variant="body2" sx={{ mt: 1.25 }}>
                Sisa{' '}
                <Box component="span" sx={{ fontWeight: 'fontWeightSemiBold' }}>
                  {formatRupiah(report.total_remaining)}
                </Box>
              </Typography>

              <Typography
                variant="caption"
                sx={{ mt: 1.5, display: 'block', color: 'text.secondary' }}
              >
                Budget itu rencana belanja, bukan uang yang disisihkan. Angka “bebas pakai” lu nggak
                berkurang karena ini.
              </Typography>
            </Card>

            {rows.map((row) => (
              <BudgetRow
                key={row.category}
                row={row}
                onEdit={() => setEditing({ category: row.category, amount: row.limit })}
                onRemove={() => onRemove(row.category)}
              />
            ))}

            <Typography variant="caption" sx={{ textAlign: 'center', color: 'text.secondary' }}>
              Di chat: “budget makan 2 juta per bulan” atau “hiburan kelebihan berapa?”
            </Typography>
          </Stack>
        )}
      </Box>

      <BudgetForm
        open={Boolean(editing)}
        initial={editing}
        onClose={() => setEditing(null)}
        onSaved={() => {
          setEditing(null);
          load();
        }}
      />
    </>
  );
}

// ----------------------------------------------------------------------

function BudgetRow({ row, onEdit, onRemove }) {
  const state = STATES[row.state] ?? STATES.ok;
  const over = row.remaining < 0;

  return (
    <Card
      variant="outlined"
      sx={{ p: 2, borderRadius: 2.5, ...(state.tint && { bgcolor: state.tint }) }}
    >
      <Stack direction="row" sx={{ gap: 1, alignItems: 'center' }}>
        <Typography variant="subtitle2" sx={{ flexGrow: 1, minWidth: 0 }} noWrap>
          {row.category}
        </Typography>

        {state.label && (
          <Box
            component="span"
            sx={{
              px: 1,
              py: 0.25,
              borderRadius: 999,
              typography: 'caption',
              fontWeight: 'fontWeightBold',
              color: `${state.colour}.contrastText`,
              bgcolor: `${state.colour}.main`,
            }}
          >
            {state.label}
          </Box>
        )}

        <IconButton size="small" aria-label={`Ubah budget ${row.category}`} onClick={onEdit}>
          <Iconify icon="solar:pen-bold" width={16} />
        </IconButton>
        <IconButton size="small" aria-label={`Hapus budget ${row.category}`} onClick={onRemove}>
          <Iconify icon="solar:trash-bin-trash-bold" width={16} />
        </IconButton>
      </Stack>

      <Typography variant="caption" sx={{ color: 'text.secondary' }}>
        {formatRupiah(row.spent)} dari {formatRupiah(row.limit)}
      </Typography>

      <LinearProgress
        variant="determinate"
        value={Math.min(row.percent, 100)}
        color={state.colour}
        sx={{ mt: 1.25, height: 10, borderRadius: 999 }}
      />

      <Stack direction="row" sx={{ mt: 0.75, justifyContent: 'space-between' }}>
        <Typography variant="caption" sx={{ color: 'text.secondary' }}>
          {row.percent}% terpakai
        </Typography>
        <Typography variant="caption" sx={{ fontWeight: 'fontWeightBold' }}>
          {over ? 'Lewat ' : 'Sisa '}
          {formatRupiah(Math.abs(row.remaining))}
        </Typography>
      </Stack>

      {over && (
        <Button
          fullWidth
          variant="outlined"
          color="inherit"
          component={RouterLink}
          href={paths.data}
          sx={{ mt: 1.5, minHeight: 44 }}
        >
          Lihat transaksinya
        </Button>
      )}
    </Card>
  );
}
