'use client';

import { useState, useEffect, useCallback } from 'react';

import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Stack from '@mui/material/Stack';
import Button from '@mui/material/Button';
import Collapse from '@mui/material/Collapse';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import LinearProgress from '@mui/material/LinearProgress';

import { paths } from 'src/routes/paths';
import { RouterLink } from 'src/routes/components';

import { formatRupiah } from 'src/utils/format-money';

import { goalsApi, accountsApi } from 'src/lib/api';

import { GoalCard } from '../../summary/goal-card';
import { SurfaceEmpty, SurfaceHeader } from '../../common';

// ----------------------------------------------------------------------

/**
 * Six is a placeholder schedule, the same one Ringkasan uses. Goals
 * carry a target date but no deposit dates yet, so the backend cannot
 * derive how many deposits are left and the caller has to say. It only
 * affects the per-deposit hint, never a saved figure.
 */
const ASSUMED_DEPOSITS = 6;

export function TargetView() {
  const [goals, setGoals] = useState([]);
  const [allocated, setAllocated] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [rows, summary] = await Promise.all([
        goalsApi.list(ASSUMED_DEPOSITS),
        accountsApi.summary(),
      ]);
      setGoals(rows);
      setAllocated(summary?.allocated ?? null);
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

  return (
    <>
      <SurfaceHeader title="Target" backHref={paths.ringkasan} />

      {loading && <LinearProgress />}

      <Box sx={{ flex: '1 1 auto', minHeight: 0, overflowY: 'auto', px: 2, pb: 3 }}>
        {error && (
          <SurfaceEmpty
            icon="solar:danger-triangle-bold"
            title="Gagal memuat target"
            body={error}
          />
        )}

        {!error && !loading && goals.length === 0 && (
          <SurfaceEmpty
            icon="lega:target"
            title="Belum ada target"
            body="Bikin lewat chat: “bikin target laptop 15 juta”. Nanti muncul kartu konfirmasi sebelum tersimpan."
          />
        )}

        {!error && goals.length > 0 && (
          <Stack sx={{ gap: 2, pt: 1 }}>
            {allocated != null && (
              <Card
                sx={{ p: 2, borderRadius: 2.5, bgcolor: 'text.primary', color: 'common.white' }}
              >
                <Typography variant="caption" sx={{ opacity: 0.64 }}>
                  Uang yang ditandai
                </Typography>
                <Typography variant="h4" sx={{ mt: 0.25, fontVariantNumeric: 'tabular-nums' }}>
                  {formatRupiah(allocated)}
                </Typography>
                <Typography variant="caption" sx={{ mt: 1.5, display: 'block', opacity: 0.72 }}>
                  Masih duduk di kantongnya masing-masing, cuma ditandai supaya nggak kepakai. Total
                  aset lu nggak naik, nggak turun.
                </Typography>
              </Card>
            )}

            {goals.map((goal) => (
              <GoalWithPlan key={goal.id} goal={goal} />
            ))}

            <Typography variant="caption" sx={{ textAlign: 'center', color: 'text.secondary' }}>
              Di chat: “sisihkan 1 juta dari BCA buat laptop”
            </Typography>
          </Stack>
        )}
      </Box>
    </>
  );
}

// ----------------------------------------------------------------------

/**
 * A goal, plus the FR11 question underneath it: given what I can
 * actually save each month, what are my options?
 */
function GoalWithPlan({ goal }) {
  const [open, setOpen] = useState(false);
  const [capacity, setCapacity] = useState('');
  const [plan, setPlan] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const onCheck = async () => {
    const value = Number(capacity);

    if (!Number.isInteger(value) || value <= 0) {
      setError('Isi kemampuan nabung per bulan, bilangan bulat rupiah.');
      return;
    }

    setBusy(true);
    setError(null);

    try {
      setPlan(await goalsApi.plan(goal.id, value));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Stack sx={{ gap: 1 }}>
      <GoalCard goal={goal} />

      <Stack direction="row" sx={{ gap: 1 }}>
        <Button
          fullWidth
          variant="outlined"
          color="inherit"
          onClick={() => setOpen((prev) => !prev)}
          sx={{ minHeight: 44 }}
        >
          {open ? 'Tutup opsi' : 'Lihat opsi'}
        </Button>
        <Button
          fullWidth
          variant="contained"
          component={RouterLink}
          href={paths.chat}
          sx={{ minHeight: 44 }}
        >
          Sisihkan
        </Button>
      </Stack>

      <Collapse in={open} unmountOnExit>
        <Card variant="outlined" sx={{ p: 2, borderRadius: 2.5 }}>
          <Typography variant="subtitle2">Kalau nabung segini per bulan</Typography>

          <Stack direction="row" sx={{ mt: 1.5, gap: 1 }}>
            <TextField
              fullWidth
              size="small"
              type="number"
              value={capacity}
              onChange={(event) => setCapacity(event.target.value)}
              placeholder="1500000"
              inputProps={{ 'aria-label': 'Kemampuan nabung per bulan' }}
            />
            <Button variant="contained" onClick={onCheck} loading={busy} sx={{ minHeight: 44 }}>
              Hitung
            </Button>
          </Stack>

          {error && (
            <Typography variant="caption" sx={{ mt: 1, display: 'block', color: 'error.main' }}>
              {error}
            </Typography>
          )}

          {plan && (
            <Box sx={{ mt: 2 }}>
              {plan.feasible ? (
                <Typography variant="body2">
                  Cukup. Perlu{' '}
                  <Box component="span" sx={{ fontWeight: 'fontWeightSemiBold' }}>
                    {plan.required_per_deposit != null
                      ? formatRupiah(plan.required_per_deposit)
                      : '—'}
                  </Box>{' '}
                  per setoran.
                </Typography>
              ) : (
                <Typography variant="body2">
                  Belum cukup dengan {formatRupiah(plan.capacity)} per bulan. Tiga jalan:
                </Typography>
              )}

              <Stack sx={{ mt: 1.5, gap: 1 }}>
                {plan.alternatives.map((option) => (
                  <Stack
                    key={option.kind}
                    direction="row"
                    sx={{
                      p: 1.5,
                      gap: 2,
                      borderRadius: 1.5,
                      alignItems: 'center',
                      bgcolor: 'background.neutral',
                      justifyContent: 'space-between',
                    }}
                  >
                    <Typography variant="body2">{option.label}</Typography>
                    <Typography
                      variant="subtitle2"
                      sx={{ whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}
                    >
                      {option.kind === 'more_deposits'
                        ? `${option.value}×`
                        : formatRupiah(option.value)}
                    </Typography>
                  </Stack>
                ))}
              </Stack>

              <Typography
                variant="caption"
                sx={{ mt: 1.5, display: 'block', color: 'text.secondary' }}
              >
                Ini hitungan saja. Nggak ada yang berubah sampai lu terapkan lewat chat.
              </Typography>
            </Box>
          )}
        </Card>
      </Collapse>
    </Stack>
  );
}
