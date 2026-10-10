import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import LinearProgress from '@mui/material/LinearProgress';

import { formatRupiah } from 'src/utils/format-money';

import { Label } from 'src/components/label';

// ----------------------------------------------------------------------

const STATUS_LABELS = {
  active: null,
  achieved: { text: 'Tercapai', color: 'success' },
  paused: { text: 'Dijeda', color: 'default' },
  cancelled: { text: 'Dibatalkan', color: 'default' },
  needs_adjustment: { text: 'Perlu penyesuaian', color: 'warning' },
};

/**
 * One savings goal.
 *
 * Every figure here comes from the backend. The progress bar is capped
 * at 100 and any excess is shown separately as `surplus`, because a bar
 * past full tells the user nothing (FR07).
 */
export function GoalCard({ goal }) {
  const status = STATUS_LABELS[goal.status];

  return (
    <Card sx={{ p: 2 }}>
      <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'start', gap: 1 }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="subtitle2" noWrap>
            {goal.name}
          </Typography>
          <Typography variant="caption" sx={{ color: 'text.secondary' }}>
            {formatRupiah(goal.saved)} dari {formatRupiah(goal.target_amount)}
          </Typography>
        </Box>

        {status && (
          <Label color={status.color} variant="soft">
            {status.text}
          </Label>
        )}
      </Stack>

      <LinearProgress
        variant="determinate"
        value={goal.percent}
        color={goal.status === 'needs_adjustment' ? 'warning' : 'primary'}
        sx={{ my: 1.5, height: 8, borderRadius: 1 }}
      />

      <Stack direction="row" sx={{ justifyContent: 'space-between', gap: 2, flexWrap: 'wrap' }}>
        <Typography variant="caption" sx={{ color: 'text.secondary' }}>
          {goal.percent}%
        </Typography>

        {goal.surplus > 0 ? (
          <Typography variant="caption" sx={{ color: 'success.main' }}>
            Lebih {formatRupiah(goal.surplus)}
          </Typography>
        ) : (
          <Typography variant="caption" sx={{ color: 'text.secondary' }}>
            Kurang {formatRupiah(goal.shortfall)}
          </Typography>
        )}
      </Stack>

      {/* Only when a schedule exists. With no remaining deposit dates the
          backend returns null rather than dividing by zero. */}
      {goal.per_deposit != null && (
        <Typography variant="caption" sx={{ mt: 1, display: 'block', color: 'text.disabled' }}>
          Perlu {formatRupiah(goal.per_deposit)} per setoran
        </Typography>
      )}
    </Card>
  );
}
