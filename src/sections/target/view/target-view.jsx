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

import { goalsApi, accountsApi } from 'src/lib/api';

import { AllocateForm } from '../allocate-form';
import {
  Pill,
  Ring,
  Money,
  HeroCard,
  BoardBody,
  BoardNote,
  BoardTitle,
  SurfaceEmpty,
} from '../../common';

// ----------------------------------------------------------------------

/**
 * Six is a placeholder schedule, the same one Ringkasan uses. Goals
 * carry a target date but no deposit dates yet, so the backend cannot
 * derive how many are left and the caller has to say. It only affects
 * the per-deposit hint, never a saved figure.
 */
const ASSUMED_DEPOSITS = 6;

const STATES = {
  active: { pill: 'ON TRACK', tone: 'good' },
  needs_adjustment: { pill: 'KETINGGALAN', tone: 'warn' },
  achieved: { pill: 'TERCAPAI', tone: 'good' },
  paused: { pill: 'DIJEDA', tone: 'info' },
  cancelled: { pill: 'DIBATALKAN', tone: 'info' },
};

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
      <BoardTitle title="Target" backHref={paths.ringkasan} />

      {loading && <LinearProgress />}

      <BoardBody>
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
            body="Bikin lewat chat: “bikin target laptop 15 juta”. Kartu konfirmasi muncul sebelum tersimpan."
          />
        )}

        {!error && goals.length > 0 && (
          <>
            {allocated != null && (
              <HeroCard
                label="Uang yang ditandai"
                amount={allocated}
                caption="Masih duduk di kantongnya masing-masing, cuma ditandai supaya nggak kepakai. Total aset lu nggak naik, nggak turun."
              />
            )}

            {goals.map((goal) => (
              <GoalCard key={goal.id} goal={goal} onChanged={load} />
            ))}

            <Typography
              sx={{ fontSize: 12, fontWeight: 600, textAlign: 'center', color: 'text.secondary' }}
            >
              Di chat: “sisihkan 1 juta dari BCA buat laptop”
            </Typography>
          </>
        )}
      </BoardBody>
    </>
  );
}

// ----------------------------------------------------------------------

function GoalCard({ goal, onChanged }) {
  const [open, setOpen] = useState(false);
  const [allocating, setAllocating] = useState(false);
  const [capacity, setCapacity] = useState('');
  const [plan, setPlan] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const state = STATES[goal.status] ?? STATES.active;
  const overdue = goal.status === 'needs_adjustment' && goal.per_deposit == null;

  const check = async () => {
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
    <Card sx={{ p: 2.25, borderRadius: 2.5 }}>
      <Stack direction="row" sx={{ gap: 2, alignItems: 'center' }}>
        <Ring percent={goal.percent} tone={goal.status === 'needs_adjustment' ? 'warn' : 'good'} />

        <Box sx={{ flexGrow: 1, minWidth: 0 }}>
          <Stack direction="row" sx={{ gap: 1, alignItems: 'center' }}>
            <Typography noWrap sx={{ fontSize: 17, fontWeight: 800 }}>
              {goal.name}
            </Typography>
            {state.pill && <Pill tone={state.tone}>{state.pill}</Pill>}
          </Stack>

          <Typography sx={{ mt: 0.5, fontSize: 15, fontWeight: 800 }}>
            <Money amount={goal.saved} sx={{ display: 'inline' }} />{' '}
            <Box component="span" sx={{ fontSize: 13, fontWeight: 600, color: 'text.secondary' }}>
              / <Money amount={goal.target_amount} plain sx={{ display: 'inline' }} />
            </Box>
          </Typography>

          <Typography sx={{ fontSize: 12, fontWeight: 600, color: 'text.secondary' }}>
            {goal.target_date
              ? new Date(goal.target_date).toLocaleDateString('id-ID', {
                  day: 'numeric',
                  month: 'short',
                  year: 'numeric',
                })
              : 'Tanpa tenggat'}
          </Typography>
        </Box>
      </Stack>

      {goal.per_deposit != null && (
        <Stack
          direction="row"
          sx={{
            mt: 1.75,
            p: 1.5,
            gap: 2,
            borderRadius: 1.75,
            alignItems: 'center',
            bgcolor: 'grey.100',
            justifyContent: 'space-between',
          }}
        >
          <Typography sx={{ fontSize: 13, fontWeight: 600, color: 'grey.700' }}>
            Perlu nabung
          </Typography>
          <Typography sx={{ fontSize: 15, fontWeight: 800 }}>
            <Money amount={goal.per_deposit} sx={{ display: 'inline' }} /> / setoran
          </Typography>
        </Stack>
      )}

      {overdue && (
        <Box sx={{ mt: 1.75 }}>
          <BoardNote tone="bad">
            Tenggatnya lewat, jadi setoran per bulan nggak bisa dihitung — nggak ada sisa waktu buat
            dibagi. Pilih tenggat baru dulu lewat chat.
          </BoardNote>
        </Box>
      )}

      <Stack direction="row" sx={{ mt: 1.75, gap: 1 }}>
        <Button
          fullWidth
          onClick={() => setOpen((prev) => !prev)}
          sx={{
            minHeight: 44,
            fontWeight: 800,
            borderRadius: 999,
            border: '1.5px solid',
            borderColor: 'grey.300',
            color: 'text.primary',
          }}
        >
          {open ? 'Tutup opsi' : 'Lihat opsi'}
        </Button>
        <Button
          fullWidth
          onClick={() => setAllocating(true)}
          sx={{
            minHeight: 44,
            fontWeight: 800,
            borderRadius: 999,
            color: 'primary.darker',
            bgcolor: 'primary.lighter',
          }}
        >
          Sisihkan
        </Button>
      </Stack>

      <Collapse in={open} unmountOnExit>
        <Box sx={{ mt: 1.75, pt: 1.75, borderTop: '1px solid', borderColor: 'grey.200' }}>
          <Typography sx={{ fontSize: 13, fontWeight: 800 }}>
            Kalau nabung segini per bulan
          </Typography>

          <Stack direction="row" sx={{ mt: 1.25, gap: 1 }}>
            <TextField
              fullWidth
              size="small"
              type="number"
              value={capacity}
              placeholder="1500000"
              onChange={(event) => setCapacity(event.target.value)}
              inputProps={{ 'aria-label': 'Kemampuan nabung per bulan' }}
            />
            <Button
              variant="contained"
              onClick={check}
              loading={busy}
              sx={{ minHeight: 44, borderRadius: 2, fontWeight: 800 }}
            >
              Hitung
            </Button>
          </Stack>

          {error && (
            <Typography sx={{ mt: 1, fontSize: 12, fontWeight: 600, color: 'error.main' }}>
              {error}
            </Typography>
          )}

          {plan && (
            <Box sx={{ mt: 1.75 }}>
              <Typography sx={{ fontSize: 13, fontWeight: 600, color: 'grey.700' }}>
                {plan.feasible ? 'Cukup dengan kemampuan itu.' : 'Belum cukup. Tiga jalan keluar:'}
              </Typography>

              <Stack sx={{ mt: 1.25, gap: 1 }}>
                {plan.alternatives.map((option) => (
                  <Stack
                    key={option.kind}
                    direction="row"
                    sx={{
                      p: 1.5,
                      gap: 2,
                      borderRadius: 1.75,
                      alignItems: 'center',
                      bgcolor: 'grey.100',
                      justifyContent: 'space-between',
                    }}
                  >
                    <Typography sx={{ fontSize: 13, fontWeight: 700 }}>{option.label}</Typography>
                    <Typography sx={{ fontSize: 13, fontWeight: 800, whiteSpace: 'nowrap' }}>
                      {option.kind === 'more_deposits' ? (
                        `${option.value}×`
                      ) : (
                        <Money amount={option.value} sx={{ display: 'inline' }} />
                      )}
                    </Typography>
                  </Stack>
                ))}
              </Stack>

              <Box sx={{ mt: 1.5 }}>
                <BoardNote tone="info">
                  Ini hitungan saja. Nggak ada yang berubah sampai lu terapkan lewat chat.
                </BoardNote>
              </Box>
            </Box>
          )}
        </Box>
      </Collapse>

      <AllocateForm
        goal={goal}
        open={allocating}
        onClose={() => setAllocating(false)}
        onSaved={() => {
          setAllocating(false);
          onChanged?.();
        }}
      />
    </Card>
  );
}
