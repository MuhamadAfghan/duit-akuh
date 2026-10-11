import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';

import { paths } from 'src/routes/paths';
import { RouterLink } from 'src/routes/components';

import { formatRupiah, formatRupiahPlain } from 'src/utils/format-money';

import { Iconify } from 'src/components/iconify';

// ----------------------------------------------------------------------

/** Below this a bar is a sliver nobody can compare; give it a floor. */
const MIN_BAR = 4;

/**
 * A spending breakdown, drawn.
 *
 * Built from the tool's own output, which is why it can be trusted
 * beside the sentence above it: the model never restates these figures,
 * it only chooses whether to ask for them.
 *
 * **Every bar prints its own number**, and the one that matters —
 * a category over its budget — says so in words as well as in amber.
 * The PRD forbids a chart that works only on hover or only by colour
 * (FR18), and the way to satisfy that is not a tooltip but a chart
 * with nothing hidden in it: there is no state in which tapping a row
 * would reveal something the row does not already say.
 *
 * No chart library. Five labelled bars are five divs, and apexcharts
 * is not installed — pulling in a charting runtime to draw a rectangle
 * would cost the chat shell's LCP budget for nothing.
 */
export function SpendingCard({ data }) {
  const categories = data?.categories ?? [];
  const total = data?.expense_total ?? 0;
  const previous = data?.previous_expense_total;

  const largest = categories.reduce((top, row) => Math.max(top, row.amount ?? 0), 0);

  return (
    <Card sx={{ width: 1, borderRadius: 2.5, overflow: 'hidden' }}>
      <Box sx={{ px: 1.875, pt: 1.625, pb: 1.75 }}>
        <Typography
          component="h3"
          sx={{
            fontSize: 10,
            fontWeight: 800,
            letterSpacing: '0.07em',
            color: 'text.secondary',
            textTransform: 'uppercase',
          }}
        >
          Pengeluaran &middot; {data?.period ?? 'periode ini'}
        </Typography>

        <Typography
          sx={{
            mt: 0.875,
            fontSize: 32,
            lineHeight: '36px',
            fontWeight: 800,
            letterSpacing: '-0.025em',
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {formatRupiah(total)}
        </Typography>

        <Delta total={total} previous={previous} />
      </Box>

      {categories.length > 0 && (
        <Stack sx={{ gap: 1.125, px: 1.875, pb: 1.625 }}>
          {categories.map((row) => (
            <CategoryBar key={row.name} row={row} largest={largest} />
          ))}
        </Stack>
      )}

      <Stack direction="row" sx={{ px: 1.875, pb: 1.75, gap: 1, alignItems: 'center' }}>
        <Box
          component={RouterLink}
          href={paths.data}
          sx={{
            px: 1.625,
            height: 36,
            display: 'flex',
            fontSize: 12,
            fontWeight: 800,
            alignItems: 'center',
            borderRadius: 999,
            border: '1.5px solid',
            borderColor: 'grey.300',
            color: 'text.primary',
            textDecoration: 'none',
          }}
        >
          {data?.transaction_count ?? 0} transaksi
        </Box>

        <Box
          component={RouterLink}
          href={paths.ringkasan}
          sx={{
            px: 1.625,
            height: 36,
            display: 'flex',
            fontSize: 12,
            fontWeight: 800,
            alignItems: 'center',
            borderRadius: 999,
            border: '1.5px solid',
            borderColor: 'grey.300',
            color: 'text.primary',
            textDecoration: 'none',
          }}
        >
          Buka Ringkasan
        </Box>
      </Stack>
    </Card>
  );
}

// ----------------------------------------------------------------------

/**
 * How this period compares with the one before it.
 *
 * The direction is said in a word as well as drawn in an arrow, and
 * coloured only after that: "naik" and "turun" are what carry it.
 */
function Delta({ total, previous }) {
  if (!Number.isInteger(previous) || previous <= 0 || total === previous) {
    return null;
  }

  const up = total > previous;
  const percent = Math.round((Math.abs(total - previous) / previous) * 100);

  return (
    <Stack direction="row" sx={{ mt: 0.5, gap: 0.625, alignItems: 'center', flexWrap: 'wrap' }}>
      <Iconify
        width={14}
        icon={up ? 'lega:arrow-up' : 'lega:arrow-down'}
        sx={{ color: up ? 'error.dark' : 'primary.dark' }}
      />
      <Typography sx={{ fontSize: 13, fontWeight: 800, color: up ? 'error.dark' : 'primary.dark' }}>
        {up ? 'naik' : 'turun'} {percent}%
      </Typography>
      <Typography sx={{ fontSize: 13, fontWeight: 600, color: 'text.secondary' }}>
        dari {formatRupiah(previous)} sebelumnya
      </Typography>
    </Stack>
  );
}

// ----------------------------------------------------------------------

function CategoryBar({ row, largest }) {
  const amount = row.amount ?? 0;
  const over = Number.isInteger(row.over) ? row.over : null;
  const width = largest > 0 ? Math.max((amount / largest) * 100, MIN_BAR) : MIN_BAR;

  return (
    <Box>
      <Stack direction="row" sx={{ gap: 1, alignItems: 'baseline' }}>
        <Typography noWrap sx={{ flex: '1 1 auto', minWidth: 0, fontSize: 13, fontWeight: 700 }}>
          {row.name}
        </Typography>
        <Typography
          sx={{
            fontSize: 13,
            fontWeight: 800,
            fontVariantNumeric: 'tabular-nums',
            color: over != null ? '#B76E00' : 'text.primary',
          }}
        >
          {formatRupiahPlain(amount)}
        </Typography>
      </Stack>

      <Box sx={{ mt: 0.5, height: 9, borderRadius: 999, bgcolor: 'grey.200', overflow: 'hidden' }}>
        <Box
          sx={{
            height: 1,
            width: `${width}%`,
            borderRadius: 999,
            bgcolor: over != null ? '#B76E00' : 'primary.main',
          }}
        />
      </Box>

      {over != null && (
        <Stack direction="row" sx={{ mt: 0.5, gap: 0.5, alignItems: 'center' }}>
          <Iconify width={12} icon="solar:danger-triangle-bold" sx={{ color: '#B76E00' }} />
          <Typography sx={{ fontSize: 11, fontWeight: 800, color: '#B76E00' }}>
            lewat budget {formatRupiah(over)}
          </Typography>
        </Stack>
      )}
    </Box>
  );
}
