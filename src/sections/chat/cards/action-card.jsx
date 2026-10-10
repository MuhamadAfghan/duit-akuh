import { varAlpha } from 'minimal-shared/utils';

import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Stack from '@mui/material/Stack';
import Button from '@mui/material/Button';
import Divider from '@mui/material/Divider';
import Typography from '@mui/material/Typography';
import CircularProgress from '@mui/material/CircularProgress';

import { formatRupiah } from 'src/utils/format-money';

import { Iconify } from 'src/components/iconify';

// ----------------------------------------------------------------------

/**
 * The in-chat confirmation card (PRD FR05, FR14, section 3).
 *
 * This is the one shape every write in the app passes through: show what
 * will change, then Konfirmasi / Ubah / Batal. Reads and simulations never
 * use it, because they change nothing.
 *
 * It is presentational only. It never computes a balance — `impact` is
 * handed to it already calculated by the backend, since the PRD requires
 * figures to come from tested functions rather than from the model or the
 * UI.
 *
 * @param {object} props
 * @param {string} props.title
 * @param {string} [props.caption] one-line restatement of what was understood
 * @param {React.ReactNode} [props.children] the editable detail rows
 * @param {Array<{label: string, before: number, after: number}>} [props.impact]
 *   balance changes in integer rupiah, shown before saving
 * @param {'draft'|'saving'|'saved'|'cancelled'|'error'} props.status
 * @param {string} [props.statusMessage] shown when status is 'saved' or 'error'
 */
export function ActionCard({
  title,
  caption,
  children,
  impact = [],
  status = 'draft',
  statusMessage,
  confirmLabel = 'Konfirmasi',
  onConfirm,
  onEdit,
  onCancel,
}) {
  const isPending = status === 'draft';
  const isSaving = status === 'saving';
  const isSettled = status === 'saved' || status === 'cancelled' || status === 'error';

  return (
    <Card
      variant="outlined"
      sx={(theme) => ({
        p: 2,
        width: 1,
        ...(status === 'error' && {
          borderColor: varAlpha(theme.vars.palette.error.mainChannel, 0.48),
        }),
        ...(status === 'cancelled' && { opacity: 0.72 }),
      })}
    >
      <Stack spacing={0.5}>
        <Typography variant="subtitle1">{title}</Typography>

        {caption && (
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            {caption}
          </Typography>
        )}
      </Stack>

      {children && <Box sx={{ mt: 2 }}>{children}</Box>}

      {/* The impact preview. The PRD requires every financial change to show
          its effect before it is saved, so this block is not decorative. */}
      {!!impact.length && isPending && (
        <>
          <Divider sx={{ my: 2, borderStyle: 'dashed' }} />

          <Stack spacing={1}>
            <Typography variant="overline" sx={{ color: 'text.secondary' }}>
              Dampak
            </Typography>

            {impact.map((row) => (
              <Stack
                key={row.label}
                direction="row"
                sx={{ alignItems: 'center', justifyContent: 'space-between', gap: 2 }}
              >
                <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                  {row.label}
                </Typography>

                <Stack direction="row" sx={{ alignItems: 'center', gap: 0.75 }}>
                  <Typography
                    variant="body2"
                    sx={{ color: 'text.disabled', textDecoration: 'line-through' }}
                  >
                    {formatRupiah(row.before)}
                  </Typography>

                  <Iconify icon="eva:arrow-ios-forward-fill" width={16} />

                  <Typography
                    variant="subtitle2"
                    sx={{ color: row.after < row.before ? 'error.main' : 'success.main' }}
                  >
                    {formatRupiah(row.after)}
                  </Typography>
                </Stack>
              </Stack>
            ))}
          </Stack>
        </>
      )}

      {isSettled && statusMessage && (
        <>
          <Divider sx={{ my: 2, borderStyle: 'dashed' }} />

          <Stack direction="row" sx={{ gap: 1, alignItems: 'flex-start' }}>
            <Iconify
              width={20}
              icon={
                status === 'saved'
                  ? 'solar:check-circle-bold'
                  : status === 'error'
                    ? 'solar:danger-triangle-bold'
                    : 'solar:close-circle-bold'
              }
              sx={{
                mt: 0.25,
                color:
                  status === 'saved'
                    ? 'success.main'
                    : status === 'error'
                      ? 'error.main'
                      : 'text.disabled',
              }}
            />

            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              {statusMessage}
            </Typography>
          </Stack>
        </>
      )}

      {(isPending || isSaving) && (
        <Stack direction="row" sx={{ mt: 2.5, gap: 1 }}>
          <Button
            fullWidth
            variant="contained"
            size="large"
            disabled={isSaving}
            onClick={onConfirm}
            startIcon={
              isSaving ? (
                <CircularProgress size={16} color="inherit" />
              ) : (
                <Iconify icon="solar:check-circle-bold" />
              )
            }
          >
            {isSaving ? 'Menyimpan' : confirmLabel}
          </Button>

          {onEdit && (
            <Button
              variant="outlined"
              size="large"
              color="inherit"
              disabled={isSaving}
              onClick={onEdit}
              aria-label="Ubah draft"
              sx={{ minWidth: 44, px: 1.5 }}
            >
              <Iconify icon="solar:pen-bold" />
            </Button>
          )}

          {onCancel && (
            <Button
              variant="outlined"
              size="large"
              color="inherit"
              disabled={isSaving}
              onClick={onCancel}
              aria-label="Batalkan draft"
              sx={{ minWidth: 44, px: 1.5 }}
            >
              <Iconify icon="mingcute:close-line" />
            </Button>
          )}
        </Stack>
      )}
    </Card>
  );
}
