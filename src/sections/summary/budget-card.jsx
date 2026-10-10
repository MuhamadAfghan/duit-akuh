import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import LinearProgress from '@mui/material/LinearProgress';

import { formatRupiah } from 'src/utils/format-money';

// ----------------------------------------------------------------------

const STATE_COLOR = { ok: 'primary', approaching: 'warning', exceeded: 'error' };

/**
 * One category budget.
 *
 * The bar is clamped at 100 because it cannot render further, but the
 * figures are not: `remaining` stays negative and the percentage keeps
 * its real value, since an overspend is the one thing a budget exists
 * to surface (FR08).
 */
export function BudgetCard({ budget }) {
  const color = STATE_COLOR[budget.state] ?? 'primary';
  const over = budget.remaining < 0;

  return (
    <Card sx={{ p: 2 }}>
      <Stack direction="row" sx={{ justifyContent: 'space-between', gap: 2 }}>
        <Typography variant="subtitle2" noWrap>
          {budget.category}
        </Typography>
        <Typography variant="caption" sx={{ color: `${color}.main`, whiteSpace: 'nowrap' }}>
          {budget.percent}%
        </Typography>
      </Stack>

      <LinearProgress
        variant="determinate"
        value={Math.min(100, budget.percent)}
        color={color}
        sx={{ my: 1.5, height: 8, borderRadius: 1 }}
      />

      <Stack direction="row" sx={{ justifyContent: 'space-between', gap: 2, flexWrap: 'wrap' }}>
        <Typography variant="caption" sx={{ color: 'text.secondary' }}>
          {formatRupiah(budget.spent)} dari {formatRupiah(budget.limit)}
        </Typography>

        <Typography
          variant="caption"
          sx={{ color: over ? 'error.main' : 'text.secondary', fontWeight: over ? 600 : 400 }}
        >
          {over
            ? `Lewat ${formatRupiah(-budget.remaining)}`
            : `Sisa ${formatRupiah(budget.remaining)}`}
        </Typography>
      </Stack>
    </Card>
  );
}

// ----------------------------------------------------------------------

/** Reminder that a budget is a plan, shown once under the list. */
export function BudgetNote() {
  return (
    <Box sx={{ px: 0.5 }}>
      <Typography variant="caption" sx={{ color: 'text.disabled' }}>
        Budget adalah rencana belanja, bukan saldo — tidak mengurangi uang bebas pakai.
      </Typography>
    </Box>
  );
}
