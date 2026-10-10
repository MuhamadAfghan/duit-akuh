'use client';

import Box from '@mui/material/Box';
import ButtonBase from '@mui/material/ButtonBase';
import Typography from '@mui/material/Typography';

import { usePathname } from 'src/routes/hooks';
import { RouterLink } from 'src/routes/components';

import { Iconify } from 'src/components/iconify';

import { appTabs } from './nav-config-app';

// ----------------------------------------------------------------------

const TAB_HEIGHT = 56;

/**
 * Bottom tab bar (PRD FR17).
 *
 * - Targets are at least 44x44 CSS px.
 * - Sits above the home indicator via safe-area-inset-bottom.
 * - `hidden` is passed when the keyboard is open, which the PRD allows, so
 *   the composer and messages keep the available height.
 */
export function BottomTabs({ hidden = false, sx, ...other }) {
  const pathname = usePathname();

  const isActive = (path) =>
    // Chat lives at '/', so only an exact match counts; the others own
    // their subtrees.
    path === '/' ? pathname === '/' : pathname.startsWith(path);

  if (hidden) {
    return null;
  }

  return (
    <Box
      component="nav"
      aria-label="Navigasi utama"
      sx={[
        (theme) => ({
          flexShrink: 0,
          display: 'flex',
          bgcolor: theme.vars.palette.background.paper,
          borderTop: `solid 1px ${theme.vars.palette.divider}`,
          pb: 'env(safe-area-inset-bottom)',
        }),
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
      {...other}
    >
      {appTabs.map((tab) => {
        const active = isActive(tab.path);

        return (
          <ButtonBase
            key={tab.path}
            component={RouterLink}
            href={tab.path}
            aria-current={active ? 'page' : undefined}
            sx={(theme) => ({
              flex: '1 1 0',
              minWidth: 44,
              minHeight: TAB_HEIGHT,
              gap: 0.25,
              py: 0.75,
              flexDirection: 'column',
              color: active ? theme.vars.palette.primary.main : theme.vars.palette.text.secondary,
            })}
          >
            <Iconify icon={tab.icon} width={24} />
            <Typography
              variant="caption"
              sx={{ fontWeight: active ? 'fontWeightSemiBold' : 'fontWeightMedium' }}
            >
              {tab.label}
            </Typography>
          </ButtonBase>
        );
      })}
    </Box>
  );
}
