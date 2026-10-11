'use client';

import { useState } from 'react';

import Tab from '@mui/material/Tab';
import Box from '@mui/material/Box';
import Tabs from '@mui/material/Tabs';
import Card from '@mui/material/Card';
import Stack from '@mui/material/Stack';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Divider from '@mui/material/Divider';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';

import { paths } from 'src/routes/paths';

import { formatRupiah } from 'src/utils/format-money';

import { simulationsApi } from 'src/lib/api';

import { SurfaceHeader } from '../../common';

// ----------------------------------------------------------------------

export function SimulasiView() {
  const [tab, setTab] = useState('nabung');

  return (
    <>
      <SurfaceHeader
        title="Simulasi"
        backHref={paths.ringkasan}
        action={
          <Box
            component="span"
            sx={{
              px: 1.25,
              py: 0.5,
              mr: 1,
              borderRadius: 999,
              typography: 'caption',
              fontWeight: 'fontWeightBold',
              color: 'info.darker',
              bgcolor: 'info.lighter',
            }}
          >
            NGGAK NGUBAH DATA
          </Box>
        }
      />

      <Box sx={{ flex: '1 1 auto', minHeight: 0, overflowY: 'auto', px: 2, pb: 3 }}>
        <Tabs value={tab} onChange={(_, value) => setTab(value)} sx={{ mb: 2 }}>
          <Tab value="nabung" label="Nabung" sx={{ minHeight: 44 }} />
          <Tab value="deposito" label="Deposito" sx={{ minHeight: 44 }} />
        </Tabs>

        {tab === 'nabung' ? <SavingForm /> : <DepositForm />}

        <Typography
          variant="caption"
          sx={{ mt: 3, display: 'block', textAlign: 'center', color: 'text.secondary' }}
        >
          Semua di halaman ini cuma hitungan. Data lu baru berubah kalau lu konfirmasi lewat chat
          (AC07).
        </Typography>
      </Box>
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
    setBusy(true);
    setError(null);

    try {
      setResult(
        await simulationsApi.saving({
          target: Number(form.target),
          initial: Number(form.initial || 0),
          periods: Number(form.periods),
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
    <Stack sx={{ gap: 2 }}>
      <Card variant="outlined" sx={{ p: 2, borderRadius: 2.5 }}>
        <Stack sx={{ gap: 2 }}>
          <Field
            label="Butuh berapa"
            value={form.target}
            onChange={(target) => setForm({ ...form, target })}
            placeholder="15000000"
          />
          <Field
            label="Sudah ada"
            value={form.initial}
            onChange={(initial) => setForm({ ...form, initial })}
          />
          <Field
            label="Nabung berapa kali"
            value={form.periods}
            onChange={(periods) => setForm({ ...form, periods })}
          />

          <Button variant="contained" onClick={run} loading={busy} sx={{ minHeight: 48 }}>
            Hitung
          </Button>
        </Stack>
      </Card>

      {error && <Alert severity="error">{error}</Alert>}

      {result && (
        <Card sx={{ p: 2.5, borderRadius: 2.5, bgcolor: 'primary.main', color: 'common.white' }}>
          <Typography variant="caption" sx={{ opacity: 0.8 }}>
            Perlu nabung tiap bulan
          </Typography>
          <Typography variant="h3" sx={{ mt: 0.25, fontVariantNumeric: 'tabular-nums' }}>
            {formatRupiah(result.per_period)}
          </Typography>

          <Typography variant="caption" sx={{ mt: 1.5, display: 'block', opacity: 0.8 }}>
            Dibulatkan ke atas. Tiga setoran {formatRupiah(3333)} nggak akan pernah jadi{' '}
            {formatRupiah(10000)}, jadi lebih baik kelebihan sedikit daripada kurang pas tenggat.
          </Typography>

          {result.overshoot > 0 && (
            <Typography variant="caption" sx={{ mt: 1, display: 'block', opacity: 0.8 }}>
              Total terkumpul {formatRupiah(result.total_saved)}, lebih{' '}
              {formatRupiah(result.overshoot)} dari target.
            </Typography>
          )}
        </Card>
      )}
    </Stack>
  );
}

// ----------------------------------------------------------------------

function DepositForm() {
  const [form, setForm] = useState({
    principal: '',
    annual_rate_percent: '4',
    months: '6',
    tax_percent: '20',
  });
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    setError(null);

    try {
      setResult(
        await simulationsApi.deposit({
          principal: Number(form.principal),
          // A string keeps the rate exact: the backend reads "4.25" as
          // 17/4 rather than the nearest binary float.
          annual_rate_percent: String(form.annual_rate_percent),
          months: Number(form.months),
          tax_percent: form.tax_percent === '' ? null : String(form.tax_percent),
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
    <Stack sx={{ gap: 2 }}>
      <Card variant="outlined" sx={{ p: 2, borderRadius: 2.5 }}>
        <Stack sx={{ gap: 2 }}>
          <Field
            label="Pokok"
            value={form.principal}
            onChange={(principal) => setForm({ ...form, principal })}
            placeholder="10000000"
          />
          <Field
            label="Bunga per tahun (%)"
            value={form.annual_rate_percent}
            onChange={(annual_rate_percent) => setForm({ ...form, annual_rate_percent })}
            decimal
          />
          <Field
            label="Berapa bulan"
            value={form.months}
            onChange={(months) => setForm({ ...form, months })}
          />
          <Field
            label="Pajak (%), kosongkan kalau belum tahu"
            value={form.tax_percent}
            onChange={(tax_percent) => setForm({ ...form, tax_percent })}
            decimal
          />

          <Button variant="contained" onClick={run} loading={busy} sx={{ minHeight: 48 }}>
            Hitung
          </Button>
        </Stack>
      </Card>

      {error && <Alert severity="error">{error}</Alert>}

      {result && (
        <Card sx={{ p: 2.5, borderRadius: 2.5, bgcolor: 'text.primary', color: 'common.white' }}>
          <Row label="Bunga kotor" value={result.gross_interest} />
          <Row label="Pajak" value={-result.tax} />
          {result.fees > 0 && <Row label="Biaya" value={-result.fees} />}

          <Divider sx={{ my: 1.5, borderColor: 'rgba(255,255,255,0.16)' }} />

          <Stack direction="row" sx={{ alignItems: 'baseline', justifyContent: 'space-between' }}>
            <Typography variant="subtitle2">Terima bersih</Typography>
            <Typography variant="h5" sx={{ fontVariantNumeric: 'tabular-nums' }}>
              {formatRupiah(result.final_value)}
            </Typography>
          </Stack>

          {!result.complete && (
            <Alert severity="warning" sx={{ mt: 2 }}>
              Tarif pajaknya belum diisi, jadi angka bersih ini <b>belum final</b>.
            </Alert>
          )}

          <Typography variant="caption" sx={{ mt: 1.5, display: 'block', opacity: 0.72 }}>
            Dihitung pakai pecahan penuh dan dibulatkan sekali di akhir, jadi setengah rupiah nggak
            hilang di tengah jalan.
          </Typography>
        </Card>
      )}
    </Stack>
  );
}

// ----------------------------------------------------------------------

function Field({ label, value, onChange, placeholder, decimal = false }) {
  return (
    <TextField
      fullWidth
      size="small"
      type="number"
      label={label}
      value={value}
      placeholder={placeholder}
      onChange={(event) => onChange(event.target.value)}
      inputProps={decimal ? { step: '0.01' } : { step: '1' }}
      slotProps={{ inputLabel: { shrink: true } }}
    />
  );
}

function Row({ label, value }) {
  return (
    <Stack direction="row" sx={{ py: 0.5, justifyContent: 'space-between' }}>
      <Typography variant="body2" sx={{ opacity: 0.72 }}>
        {label}
      </Typography>
      <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums' }}>
        {formatRupiah(value)}
      </Typography>
    </Stack>
  );
}
