'use client';

import { useState, useEffect, useCallback } from 'react';

import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Stack from '@mui/material/Stack';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';
import IconButton from '@mui/material/IconButton';

import { paths } from 'src/routes/paths';
import { RouterLink } from 'src/routes/components';

import { budgetsApi } from 'src/lib/api';

import { Iconify } from 'src/components/iconify';

import { BudgetForm } from '../budget-form';
import {
  Bar,
  Pill,
  Money,
  Loading,
  BoardBody,
  BoardNote,
  BoardTitle,
  FilterChip,
  BoardAction,
  SurfaceEmpty,
  SkeletonCard,
  SkeletonRows,
} from '../../common';

// ----------------------------------------------------------------------

/**
 * Three states, each told in words as well as colour. Colour alone
 * fails anyone who cannot separate these hues, which PRD section 12
 * rules out.
 */
const STATES = {
  ok: { pill: null, bar: 'good', bg: null, fg: 'text.secondary' },
  approaching: { pill: 'TIPIS', tone: 'warn', bar: 'warn', bg: '#FFFBEB', fg: '#6B4F00' },
  exceeded: { pill: 'LEWAT', tone: 'bad', bar: 'bad', bg: '#FDF0F0', fg: '#8E1212' },
};

const PERIODS = [
  { value: 'bulan_ini', label: 'Bulan ini' },
  { value: 'bulan_lalu', label: 'Bulan lalu' },
  { value: 'tahun_ini', label: 'Tahun ini' },
];

export function BudgetView() {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(null);
  const [period, setPeriod] = useState('bulan_ini');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setReport(await budgetsApi.list(period));
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => {
    load();
  }, [load]);

  const remove = async (category) => {
    try {
      await budgetsApi.remove(category);
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  const rows = report?.budgets ?? [];
  const used = report?.total_limit ? (report.total_spent / report.total_limit) * 100 : 0;

  return (
    <>
      <BoardTitle
        title="Budget"
        backHref={paths.ringkasan}
        action={
          <Stack direction="row" sx={{ gap: 1, alignItems: 'center' }}>
            <FilterChip value={period} onChange={setPeriod} options={PERIODS} />
            <BoardAction
              icon="lega:plus"
              label="Atur budget"
              onClick={() => setEditing({ category: '', amount: '' })}
            />
          </Stack>
        }
      />

      <BoardBody>
        {loading && (
          <Loading label="Memuat budget…">
            <SkeletonCard height={132} />
            <SkeletonRows rows={4} />
          </Loading>
        )}
        {error && (
          <SurfaceEmpty
            icon="solar:danger-triangle-bold"
            title="Gagal memuat budget"
            body={error}
          />
        )}

        {!error && !loading && rows.length === 0 && (
          <SurfaceEmpty
            icon="lega:chart"
            title="Belum ada budget"
            body="Atur lewat tombol di atas, atau ketik di chat: “budget makan 2 juta per bulan”."
          />
        )}

        {!error && rows.length > 0 && (
          <>
            <Card sx={{ p: 2.5, borderRadius: 3 }}>
              <Stack direction="row" sx={{ gap: 2, alignItems: 'flex-end' }}>
                <Box sx={{ flexGrow: 1 }}>
                  <Typography sx={{ fontSize: 13, fontWeight: 600, color: 'text.secondary' }}>
                    Kepakai {report.label.toLowerCase()}
                  </Typography>
                  <Money
                    amount={report.total_spent}
                    plain
                    sx={{ mt: 0.25, fontSize: 34, lineHeight: '40px', fontWeight: 800 }}
                  />
                </Box>
                <Typography
                  sx={{ fontSize: 15, fontWeight: 700, color: 'text.secondary', pb: 0.5 }}
                >
                  / <Money amount={report.total_limit} plain sx={{ display: 'inline' }} />
                </Typography>
              </Stack>

              <Box sx={{ mt: 1.75 }}>
                <Bar value={used} height={14} />
              </Box>

              <Typography sx={{ mt: 1.25, fontSize: 13, fontWeight: 700 }}>
                Sisa <Money amount={report.total_remaining} sx={{ display: 'inline' }} />
              </Typography>

              <Box sx={{ mt: 1.75 }}>
                <BoardNote>
                  Budget itu rencana belanja, bukan uang yang disisihkan. Angka{' '}
                  <strong>bebas pakai</strong> lu nggak berkurang karena ini.
                </BoardNote>
              </Box>
            </Card>

            <Card sx={{ borderRadius: 2.5, overflow: 'hidden' }}>
              {rows.map((row, index) => (
                <BudgetRow
                  key={row.category}
                  row={row}
                  first={index === 0}
                  onEdit={() => setEditing({ category: row.category, amount: row.limit })}
                  onRemove={() => remove(row.category)}
                />
              ))}
            </Card>

            <Typography
              sx={{ fontSize: 12, fontWeight: 600, textAlign: 'center', color: 'text.secondary' }}
            >
              Di chat: “budget makan 2 juta per bulan” atau “hiburan kelebihan berapa?”
            </Typography>
          </>
        )}
      </BoardBody>

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

function BudgetRow({ row, first, onEdit, onRemove }) {
  const state = STATES[row.state] ?? STATES.ok;
  const over = row.remaining < 0;

  return (
    <Box
      sx={{
        p: 2,
        ...(state.bg && { bgcolor: state.bg }),
        ...(!first && { borderTop: '1px solid', borderColor: 'grey.200' }),
      }}
    >
      <Stack direction="row" sx={{ gap: 1, alignItems: 'center' }}>
        <Typography noWrap sx={{ flexGrow: 1, minWidth: 0, fontSize: 15, fontWeight: 800 }}>
          {row.category}
        </Typography>

        {state.pill && <Pill tone={state.tone}>{state.pill}</Pill>}

        <IconButton
          size="small"
          aria-label={`Ubah budget ${row.category}`}
          onClick={onEdit}
          sx={{ color: 'inherit' }}
        >
          <Iconify icon="solar:pen-bold" width={16} />
        </IconButton>
        <IconButton
          size="small"
          aria-label={`Hapus budget ${row.category}`}
          onClick={onRemove}
          sx={{ color: 'inherit' }}
        >
          <Iconify icon="solar:trash-bin-trash-bold" width={16} />
        </IconButton>
      </Stack>

      <Typography sx={{ fontSize: 12, fontWeight: 600, color: state.fg }}>
        <Money amount={row.spent} plain sx={{ display: 'inline' }} /> dari{' '}
        <Money amount={row.limit} plain sx={{ display: 'inline' }} />
      </Typography>

      <Box sx={{ mt: 1.25 }}>
        <Bar value={Math.min(row.percent, 100)} tone={state.bar} />
      </Box>

      <Stack direction="row" sx={{ mt: 0.75, gap: 2, justifyContent: 'space-between' }}>
        <Typography sx={{ fontSize: 12, fontWeight: 600, color: state.fg }}>
          {row.percent}% terpakai
        </Typography>
        <Typography sx={{ fontSize: 12, fontWeight: 800, color: state.fg }}>
          {over ? 'Lewat ' : 'Sisa '}
          <Money amount={Math.abs(row.remaining)} plain sx={{ display: 'inline' }} />
        </Typography>
      </Stack>

      {over && (
        <Button
          fullWidth
          component={RouterLink}
          href={paths.data}
          sx={{
            mt: 1.5,
            minHeight: 44,
            fontWeight: 800,
            borderRadius: 999,
            color: 'common.white',
            bgcolor: 'grey.800',
            '&:hover': { bgcolor: 'grey.700' },
          }}
        >
          Lihat transaksinya
        </Button>
      )}
    </Box>
  );
}
