import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import IconButton from '@mui/material/IconButton';

import { formatRupiahPlain } from 'src/utils/format-money';

import { CONFIG } from 'src/global-config';
import { AppMenuButton } from 'src/layouts/app/app-menu';

import { Iconify } from 'src/components/iconify';

// ----------------------------------------------------------------------

/**
 * Chat header.
 *
 * Two lines in one 44px row: the name, and under it the one figure the
 * product exists to produce. The free-to-spend number used to be a
 * chip on the right, which worked until the menu button needed that
 * corner. Moving it under the title is not a demotion — it reads as
 * the app's current state rather than as a control, which is what it
 * is, and it survives a long status line instead of being pushed out
 * by one.
 *
 * The subtitle slot is shared, in priority order: trouble reaching the
 * server, then what is missing before the number means anything, then
 * the number. They are mutually exclusive by nature — "bebas pakai
 * Rp0" while offline is a lie, and before the first wallet exists it is
 * true but useless.
 *
 * The title is a button now that a user can have several threads. It
 * carries the chevron rather than sitting beside one, so the whole
 * two-line block is the target — the thread's name and the figure
 * under it are one thing you tap, not a label with a control glued on.
 */
export function ChatHeader({ status, freeToSpend, hint, title, onOpenSessions, onNewChat }) {
  return (
    <Box
      component="header"
      sx={{
        px: 1.5,
        gap: 0.75,
        flexShrink: 0,
        display: 'flex',
        alignItems: 'center',
        pt: 'calc(env(safe-area-inset-top) + 12px)',
        pb: 1.5,
        bgcolor: 'background.paper',
        borderBottom: '1px solid',
        borderColor: 'grey.200',
      }}
    >
      <Stack
        direction="row"
        component={onOpenSessions ? 'button' : 'div'}
        onClick={onOpenSessions}
        aria-label={onOpenSessions ? 'Ganti atau cari chat' : undefined}
        sx={{
          p: 0,
          gap: 1.25,
          border: 0,
          flexGrow: 1,
          minWidth: 0,
          minHeight: 44,
          textAlign: 'left',
          alignItems: 'center',
          bgcolor: 'transparent',
          ...(onOpenSessions && { cursor: 'pointer' }),
        }}
      >
        <Box
          aria-hidden
          sx={(theme) => ({
            width: 30,
            height: 30,
            flexShrink: 0,
            display: 'flex',
            borderRadius: '50%',
            alignItems: 'center',
            justifyContent: 'center',
            bgcolor: theme.vars.palette.primary.lighter,
          })}
        >
          <Box
            sx={(theme) => ({
              width: 11,
              height: 11,
              borderRadius: '50%',
              bgcolor: theme.vars.palette.primary.main,
            })}
          />
        </Box>

        <Box sx={{ minWidth: 0 }}>
          <Stack direction="row" sx={{ gap: 0.5, minWidth: 0, alignItems: 'center' }}>
            <Typography
              component="h1"
              noWrap
              sx={{ fontSize: 16, fontWeight: 800, letterSpacing: '-0.01em' }}
            >
              {title || CONFIG.appName}
              {!title && (
                <Box component="span" sx={{ color: 'primary.main' }}>
                  .
                </Box>
              )}
            </Typography>

            {onOpenSessions && (
              <Iconify
                width={15}
                icon="eva:arrow-ios-downward-fill"
                sx={{ flexShrink: 0, color: 'text.secondary' }}
              />
            )}
          </Stack>

          <Subtitle status={status} hint={hint} freeToSpend={freeToSpend} />
        </Box>
      </Stack>

      {onNewChat && (
        <IconButton
          onClick={onNewChat}
          aria-label="Mulai chat baru"
          sx={{ width: 44, height: 44, flexShrink: 0, color: 'text.primary' }}
        >
          <Iconify icon="solar:pen-bold" width={21} />
        </IconButton>
      )}

      <AppMenuButton />
    </Box>
  );
}

// ----------------------------------------------------------------------

function Subtitle({ status, hint, freeToSpend }) {
  if (status) {
    return (
      <Typography noWrap sx={{ fontSize: 12, fontWeight: 700, color: 'text.secondary' }}>
        {status}
      </Typography>
    );
  }

  if (hint) {
    return (
      <Typography noWrap sx={{ fontSize: 12, fontWeight: 700, color: 'text.secondary' }}>
        {hint}
      </Typography>
    );
  }

  if (freeToSpend == null) {
    return null;
  }

  return (
    <Stack direction="row" sx={{ gap: 0.625, alignItems: 'baseline' }}>
      <Box component="span" sx={{ fontSize: 12, fontWeight: 700, color: 'text.secondary' }}>
        bebas pakai
      </Box>
      {/* `primary.dark`, not `primary.main`: the brand green is 3.6:1 on
          white, which is fine for a fill and short of AA for 12px text. */}
      <Box
        component="span"
        sx={{
          fontSize: 12,
          fontWeight: 800,
          color: 'primary.dark',
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {formatRupiahPlain(freeToSpend)}
      </Box>
    </Stack>
  );
}
