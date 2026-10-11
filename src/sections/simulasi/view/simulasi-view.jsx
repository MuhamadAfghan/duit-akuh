'use client';

import { useState } from 'react';

import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Stack from '@mui/material/Stack';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';

import { paths } from 'src/routes/paths';

import { simulationsApi } from 'src/lib/api';

import { Pill, Money, BoardBody, BoardNote, BoardTitle } from '../../common';

// ----------------------------------------------------------------------

export function SimulasiView() {
  const [mode, setMode] = useState('nabung');

  return (
    <>
      <BoardTitle
        title="Simulasi"
        backHref={paths.ringkasan}
        action={
          <Box sx={{ mr: 1 }}>
            <Pill tone="info">NGGAK NGUBAH DATA</Pill>
          </Box>
        }
      />

      <BoardBody>
        <Box
          role="group"
          aria-label="Jenis simulasi"
          sx={{
            p: 0.5,
            gap: 0.5,
            display: 'grid',
            borderRadius: 999,
            bgcolor: 'grey.200',
            gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
          }}
        >
          {[
            { key: 'nabung', label: 'Nabung' },
            { key: 'deposito', label: 'Deposito' },
          ].map((item) => {
            const active = mode === item.key;

            return (
              <Box
                key={item.key}
                component="button"
                type="button"
                aria-pressed={active}
                onClick={() => setMode(item.key)}
                sx={{
                  border: 'none',
                  minHeight: 40,
                  fontSize: 14,
                  fontWeight: 800,
                  cursor: 'pointer',
                  borderRadius: 999,
                  color: active ? 'common.white' : 'text.secondary',
                  bgcolor: active ? 'grey.800' : 'transparent',
                }}
              >
                {item.label}
              </Box>
            );
          })}
        </Box>

        {mode === 'nabung' ? <SavingForm /> : <DepositForm />}

        <Typography
          sx={{
            fontSize: 12,
            lineHeight: 1.5,
            fontWeight: 600,
            textAlign: 'center',
            color: 'text.secondary',
          }}
        >
          Semua di halaman ini cuma hitungan. Data lu baru berubah kalau lu konfirmasi lewat chat
          (AC07).
        </Typography>
      </BoardBody>
    </>
  );
}

// ----------------------------------------------------------------------

function SavingForm() {
  const [form, setForm] = useState({ target: '', initial: '0', periods: '6' });
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    const target = Number(form.target);

    // Caught here rather than by the server: an empty field answered
    // with "Input should be greater than 0" after a round trip is the
    // form failing to do its job.
    if (!Number.isInteger(target) || target <= 0) {
      setError('Isi dulu berapa yang lu butuhin.');
      setResult(null);
      return;
    }

    setBusy(true);
    setError(null);

    try {
      setResult(
        await simulationsApi.saving({
          target,
          initial: Number(form.initial || 0),
          periods: Number(form.periods || 1),
        })
      );
    } catch (err) {
      setError(err.message);
      setResult(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Card sx={{ p: 2.25, borderRadius: 2.5 }}>
        <Stack sx={{ gap: 2 }}>
          <Num
            label="Butuh berapa"
            value={form.target}
            placeholder="15000000"
            onChange={(target) => setForm({ ...form, target })}
          />
          <Num
            label="Sudah ada"
            value={form.initial}
            onChange={(initial) => setForm({ ...form, initial })}
          />
          <Num
            label="Nabung berapa kali"
            value={form.periods}
            onChange={(periods) => setForm({ ...form, periods })}
          />

          <Button
            onClick={run}
            loading={busy}
            sx={{
              minHeight: 48,
              fontWeight: 800,
              borderRadius: 999,
              color: 'common.white',
              bgcolor: 'grey.800',
              '&:hover': { bgcolor: 'grey.700' },
            }}
          >
            Hitung
          </Button>
        </Stack>
      </Card>

      {error && <Alert severity="error">{error}</Alert>}

      {result && (
        <Card sx={{ p: 2.5, borderRadius: 3, bgcolor: 'primary.main', color: 'common.white' }}>
          <Typography sx={{ fontSize: 13, fontWeight: 700, opacity: 0.85 }}>
            Perlu nabung tiap bulan
          </Typography>
          <Money
            amount={result.per_period}
            sx={{ mt: 0.25, fontSize: 38, lineHeight: '44px', fontWeight: 800 }}
          />
          <Typography
            sx={{ mt: 1.25, fontSize: 12, lineHeight: 1.5, fontWeight: 600, opacity: 0.85 }}
          >
            Dibulatkan ke atas: tiga setoran 3.333 nggak akan pernah jadi 10.000, jadi lebih baik
            kelebihan sedikit daripada kurang pas tenggat.
          </Typography>
        </Card>
      )}
    </>
  );
}

// ----------------------------------------------------------------------

function DepositForm() {
  const [form, setForm] = useState({
    principal: '',
    rate: '4',
    months: '6',
    tax: '20',
  });
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    const principal = Number(form.principal);

    if (!Number.isInteger(principal) || principal <= 0) {
      setError('Isi dulu pokok depositonya.');
      setResult(null);
      return;
    }

    setBusy(true);
    setError(null);

    try {
      setResult(
        await simulationsApi.deposit({
          principal,
          // Sent as a string so the backend reads "4.25" as 17/4 rather
          // than the nearest binary float.
          annual_rate_percent: String(form.rate || '0'),
          months: Number(form.months || 1),
          tax_percent: form.tax === '' ? null : String(form.tax),
        })
      );
    } catch (err) {
      setError(err.message);
      setResult(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Card sx={{ p: 2.25, borderRadius: 2.5 }}>
        <Stack sx={{ gap: 2 }}>
          <Num
            label="Pokok"
            value={form.principal}
            placeholder="10000000"
            onChange={(principal) => setForm({ ...form, principal })}
          />
          <Num
            label="Bunga per tahun (%)"
            value={form.rate}
            decimal
            onChange={(rate) => setForm({ ...form, rate })}
          />
          <Num
            label="Berapa bulan"
            value={form.months}
            onChange={(months) => setForm({ ...form, months })}
          />
          <Num
            label="Pajak (%) — kosongkan kalau belum tahu"
            value={form.tax}
            decimal
            onChange={(tax) => setForm({ ...form, tax })}
          />

          <Button
            onClick={run}
            loading={busy}
            sx={{
              minHeight: 48,
              fontWeight: 800,
              borderRadius: 999,
              color: 'common.white',
              bgcolor: 'grey.800',
              '&:hover': { bgcolor: 'grey.700' },
            }}
          >
            Hitung
          </Button>
        </Stack>
      </Card>

      {error && <Alert severity="error">{error}</Alert>}

      {result && (
        <Card sx={{ p: 2.5, borderRadius: 3, bgcolor: 'grey.800', color: 'common.white' }}>
          <Line label="Bunga kotor" amount={result.gross_interest} />
          <Line label="Pajak" amount={-result.tax} />
          {result.fees > 0 && <Line label="Biaya" amount={-result.fees} />}

          <Stack
            direction="row"
            sx={{
              mt: 1.5,
              pt: 1.5,
              gap: 2,
              alignItems: 'baseline',
              justifyContent: 'space-between',
              borderTop: '1px solid rgba(255,255,255,0.16)',
            }}
          >
            <Typography sx={{ fontSize: 14, fontWeight: 800 }}>Terima bersih</Typography>
            <Money amount={result.final_value} sx={{ fontSize: 20, fontWeight: 800 }} />
          </Stack>

          {!result.complete && (
            <Box sx={{ mt: 1.75 }}>
              <BoardNote tone="warn">
                Tarif pajaknya belum diisi, jadi angka bersih ini <strong>belum final</strong>.
              </BoardNote>
            </Box>
          )}

          <Typography
            sx={{ mt: 1.5, fontSize: 12, lineHeight: 1.5, fontWeight: 600, color: 'grey.500' }}
          >
            Dihitung pakai pecahan penuh dan dibulatkan sekali di akhir, jadi setengah rupiah nggak
            hilang di tengah jalan.
          </Typography>
        </Card>
      )}
    </>
  );
}

// ----------------------------------------------------------------------

function Num({ label, value, onChange, placeholder, decimal = false }) {
  return (
    <TextField
      fullWidth
      size="small"
      type="number"
      label={label}
      value={value}
      placeholder={placeholder}
      onChange={(event) => onChange(event.target.value)}
      inputProps={{ step: decimal ? '0.01' : '1' }}
      slotProps={{ inputLabel: { shrink: true } }}
    />
  );
}

function Line({ label, amount }) {
  return (
    <Stack direction="row" sx={{ py: 0.5, gap: 2, justifyContent: 'space-between' }}>
      <Typography sx={{ fontSize: 13, fontWeight: 600, color: 'grey.400' }}>{label}</Typography>
      <Money amount={amount} sx={{ fontSize: 13, fontWeight: 700 }} />
    </Stack>
  );
}
