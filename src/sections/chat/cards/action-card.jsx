import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Stack from '@mui/material/Stack';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';

import { Iconify } from 'src/components/iconify';
import { SwipeConfirm } from 'src/components/swipe-confirm';

import { Pill, Money } from '../../common';

// ----------------------------------------------------------------------

/**
 * The in-chat confirmation card (PRD FR05, FR14, section 3).
 *
 * Every write in the app passes through this one shape: say what will
 * change, then let the person commit it. Reads and simulations never
 * use it, because they change nothing.
 *
 * It is presentational. It never computes a balance — `amount` and the
 * body rows arrive already calculated by the backend, because the PRD
 * requires figures to come from tested functions rather than from the
 * model or the UI.
 *
 * The tinted head is not decoration: it is where the amount lives, and
 * the amount is the thing a person checks before committing. Putting it
 * in its own zone means you can read the card in one glance and stop.
 */

const TONES = {
  neutral: { head: 'grey.100', amount: 'text.primary', kicker: 'text.secondary' },
  good: { head: 'primary.lighter', amount: 'primary.darker', kicker: 'primary.dark' },
  bad: { head: '#FDF0F0', amount: '#8E1212', kicker: '#8E1212' },
};

export function ActionCard({
  kicker,
  amount,
  amountSigned = false,
  subtitle,
  tone = 'neutral',
  children,
  status = 'draft',
  statusMessage,
  confirmLabel = 'Geser untuk konfirmasi',
  blockedReason = null,
  destructive = false,
  onConfirm,
  onRevise,
  onCancel,
}) {
  const isPending = status === 'draft';
  const isSaving = status === 'saving';
  const isSettled = !isPending && !isSaving;

  const tone_ = TONES[tone] ?? TONES.neutral;

  return (
    <Card
      sx={{
        width: 1,
        borderRadius: 3,
        overflow: 'hidden',
        ...(status === 'cancelled' && { opacity: 0.72 }),
      }}
    >
      <Box sx={{ px: 2.25, py: 2, bgcolor: tone_.head }}>
        <Stack direction="row" sx={{ gap: 1, alignItems: 'center' }}>
          <Typography
            sx={{
              flexGrow: 1,
              minWidth: 0,
              fontSize: 11,
              fontWeight: 800,
              letterSpacing: '0.06em',
              color: tone_.kicker,
            }}
            noWrap
          >
            {kicker}
          </Typography>

          {isPending && <Pill>BELUM TERSIMPAN</Pill>}
        </Stack>

        {amount != null && (
          <Money
            amount={amount}
            signed={amountSigned}
            sx={{ mt: 1, fontSize: 36, lineHeight: '40px', fontWeight: 800, color: tone_.amount }}
          />
        )}

        {subtitle && (
          <Typography sx={{ mt: 0.75, fontSize: 14, fontWeight: 600, color: tone_.kicker }}>
            {subtitle}
          </Typography>
        )}
      </Box>

      {children && <Box sx={{ px: 2.25, pt: 2 }}>{children}</Box>}

      {isSettled && statusMessage && (
        <Stack direction="row" sx={{ px: 2.25, py: 2, gap: 1.25, alignItems: 'flex-start' }}>
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
              mt: 0.1,
              flexShrink: 0,
              color:
                status === 'saved'
                  ? 'primary.main'
                  : status === 'error'
                    ? 'error.main'
                    : 'text.disabled',
            }}
          />
          <Typography sx={{ fontSize: 13, fontWeight: 600, color: 'text.secondary' }}>
            {statusMessage}
          </Typography>
        </Stack>
      )}

      {(isPending || isSaving) && (
        <Box sx={{ px: 2.25, pt: 2, pb: 2.25 }}>
          {destructive ? (
            <Stack direction="row" sx={{ gap: 1 }}>
              <Button
                fullWidth
                onClick={onConfirm}
                loading={isSaving}
                sx={{
                  height: 48,
                  fontSize: 15,
                  fontWeight: 800,
                  borderRadius: 999,
                  color: 'common.white',
                  bgcolor: '#C01818',
                  '&:hover': { bgcolor: '#8E1212' },
                }}
              >
                {confirmLabel}
              </Button>
              <Button
                onClick={onCancel}
                disabled={isSaving}
                sx={{
                  px: 2.5,
                  height: 48,
                  fontSize: 15,
                  fontWeight: 800,
                  borderRadius: 999,
                  border: '1.5px solid',
                  borderColor: 'grey.300',
                  color: 'text.primary',
                }}
              >
                Jangan
              </Button>
            </Stack>
          ) : (
            <>
              {/* A locked track rather than a hidden one: the swipe is
                  where the eye goes, so its absence would read as a
                  card that cannot be saved at all. Saying what is
                  missing turns it into an instruction. */}
              <SwipeConfirm
                label={blockedReason ?? confirmLabel}
                busy={isSaving}
                disabled={isSaving || Boolean(blockedReason)}
                onConfirm={onConfirm}
              />

              {/* The way out of a wrong number. It sits beside Batal
                  rather than above the swipe because reading the card
                  comes first: you check the figure, and only then
                  decide whether to commit it, fix it, or drop it. */}
              {(onRevise || onCancel) && (
                <Stack direction="row" sx={{ mt: 1, gap: 1 }}>
                  {onRevise && (
                    <Button
                      fullWidth
                      onClick={onRevise}
                      disabled={isSaving}
                      startIcon={<Iconify icon="solar:pen-bold" width={18} />}
                      sx={{
                        minHeight: 44,
                        fontWeight: 800,
                        borderRadius: 999,
                        border: '1.5px solid',
                        borderColor: 'grey.300',
                        color: 'text.primary',
                      }}
                    >
                      Ubah dulu
                    </Button>
                  )}

                  {onCancel && (
                    <Button
                      fullWidth={!onRevise}
                      onClick={onCancel}
                      disabled={isSaving}
                      sx={{
                        px: 2.5,
                        minHeight: 44,
                        fontWeight: 700,
                        borderRadius: 999,
                        color: 'text.secondary',
                      }}
                    >
                      Batal
                    </Button>
                  )}
                </Stack>
              )}
            </>
          )}
        </Box>
      )}
    </Card>
  );
}

// ----------------------------------------------------------------------

/** A before → after line, the way every board draws an impact. */
export function ImpactLine({ label, before, after }) {
  return (
    <Stack direction="row" sx={{ gap: 1, alignItems: 'baseline', flexWrap: 'wrap' }}>
      <Typography sx={{ fontSize: 13, fontWeight: 600, color: 'text.secondary' }}>
        {label}
      </Typography>
      <Money
        amount={before}
        plain
        sx={{ fontSize: 13, fontWeight: 600, color: 'text.secondary' }}
      />
      <Box component="span" sx={{ color: 'text.disabled' }}>
        →
      </Box>
      <Money amount={after} plain sx={{ fontSize: 13, fontWeight: 800 }} />
    </Stack>
  );
}

/** Two boxes with an arrow between them, for anything two-sided. */
export function TwoSided({ from, to }) {
  return (
    <Stack direction="row" sx={{ gap: 1.25, alignItems: 'center' }}>
      <Side caption="DARI" name={from.name} amount={-from.amount} tone="bad" />

      <Box
        sx={{
          width: 32,
          height: 32,
          flexShrink: 0,
          display: 'grid',
          placeItems: 'center',
          borderRadius: '50%',
          color: 'common.white',
          bgcolor: '#00B6E6',
        }}
      >
        <Iconify icon="lega:arrow-right" width={17} />
      </Box>

      <Side caption="KE" name={to.name} amount={to.amount} tone="good" />
    </Stack>
  );
}

function Side({ caption, name, amount, tone }) {
  return (
    <Box sx={{ p: 1.5, flexGrow: 1, minWidth: 0, borderRadius: 2, bgcolor: 'grey.100' }}>
      <Typography
        sx={{ fontSize: 10, fontWeight: 800, letterSpacing: '0.06em', color: 'text.secondary' }}
      >
        {caption}
      </Typography>
      <Typography noWrap sx={{ mt: 0.4, fontSize: 15, fontWeight: 800 }}>
        {name ?? '—'}
      </Typography>
      <Money
        amount={amount}
        signed
        plain={false}
        sx={{ fontSize: 13, fontWeight: 700, color: tone === 'bad' ? '#8E1212' : 'primary.dark' }}
      />
    </Box>
  );
}

/** A labelled figure on its own row, for details that are not money. */
export function DetailRow({ label, value }) {
  if (value == null || value === '') {
    return null;
  }

  return (
    <Stack direction="row" sx={{ gap: 2, justifyContent: 'space-between' }}>
      <Typography sx={{ fontSize: 14, fontWeight: 600, color: 'text.secondary' }}>
        {label}
      </Typography>
      <Typography sx={{ fontSize: 14, fontWeight: 700, textAlign: 'right' }}>{value}</Typography>
    </Stack>
  );
}
