'use client';

import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';

import { paths } from 'src/routes/paths';
import { usePathname } from 'src/routes/hooks';
import { RouterLink } from 'src/routes/components';

import { Iconify } from 'src/components/iconify';

import { appTabs } from './nav-config-app';

// ----------------------------------------------------------------------

/** Pill height. The shell reserves this plus its bottom margin. */
export const TAB_HEIGHT = 64;

/**
 * The bottom bar: a floating dark pill with a raised centre button.
 *
 * Two deliberate departures from a plain tab strip. It floats, so the
 * content behind it reads as one continuous surface rather than a page
 * squeezed above a chrome bar. And the centre slot is not a tab at all
 * — it is the way to record something by hand, given equal footing with
 * the chat so "manual or chat" is a real choice rather than a fallback
 * buried in a menu.
 */
export function BottomTabs({ hidden }) {
  const pathname = usePathname();

  if (hidden) {
    return null;
  }

  const isActive = (path) => (path === '/' ? pathname === '/' : pathname.startsWith(path));

  return (
    <Box
      component="nav"
      aria-label="Navigasi utama"
      sx={{
        flexShrink: 0,
        mx: 1.75,
        mb: 'calc(env(safe-area-inset-bottom) + 14px)',
        height: TAB_HEIGHT,
        display: 'grid',
        gridTemplateColumns: 'repeat(5, minmax(0, 1fr))',
        alignItems: 'center',
        borderRadius: 999,
        bgcolor: 'grey.800',
        boxShadow: '0 14px 28px -14px rgba(11,13,14,0.7)',
      }}
    >
      {appTabs.slice(0, 2).map((tab) => (
        <Tab key={tab.path} tab={tab} active={isActive(tab.path)} />
      ))}

      <Box
        component={RouterLink}
        href={paths.catat}
        aria-label="Catat manual"
        sx={{
          width: 48,
          height: 48,
          display: 'flex',
          justifySelf: 'center',
          borderRadius: '50%',
          alignItems: 'center',
          color: 'primary.contrastText',
          bgcolor: 'primary.main',
          justifyContent: 'center',
        }}
      >
        <Iconify icon="lega:plus" width={24} />
      </Box>

      {appTabs.slice(2).map((tab) => (
        <Tab key={tab.path} tab={tab} active={isActive(tab.path)} />
      ))}
    </Box>
  );
}

// ----------------------------------------------------------------------

function Tab({ tab, active }) {
  return (
    <Stack
      component={RouterLink}
      href={tab.path}
      aria-current={active ? 'page' : undefined}
      sx={{
        gap: 0.4,
        minHeight: 48,
        alignItems: 'center',
        justifyContent: 'center',
        textDecoration: 'none',
        fontSize: 10,
        fontWeight: active ? 800 : 700,
        color: active ? 'common.white' : 'grey.500',
      }}
    >
      <Iconify icon={tab.icon} width={22} />
      {tab.label}
    </Stack>
  );
}
