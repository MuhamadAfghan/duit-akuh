'use client';

import { useId, useState, useCallback } from 'react';

import Box from '@mui/material/Box';
import Popover from '@mui/material/Popover';
import IconButton from '@mui/material/IconButton';

import { usePathname } from 'src/routes/hooks';
import { RouterLink } from 'src/routes/components';

import { Iconify } from 'src/components/iconify';

import { appMenuTiles } from './nav-config-app';

// ----------------------------------------------------------------------

/**
 * The chat's way out of itself.
 *
 * Only the chat uses this. Every other surface keeps the bottom tab
 * bar; the chat drops it because a composer, a keyboard and a thread
 * already want the whole height, and a floating bar over a scrolling
 * conversation is the one place it gets in the way.
 *
 * So this is not a shortcut to the bar — it is a replacement for it on
 * one screen, which is why it holds all eight destinations rather than
 * the bar's four. A grid rather than eight rows: eight rows is a scroll
 * on a small phone and reads as a settings screen, while square targets
 * read as a launcher, which is what this is.
 */
export function AppMenuButton() {
  const pathname = usePathname();
  const popoverId = useId();

  const [anchorEl, setAnchorEl] = useState(null);

  const open = useCallback((event) => setAnchorEl(event.currentTarget), []);
  const close = useCallback(() => setAnchorEl(null), []);

  const isOpen = Boolean(anchorEl);

  // `trailingSlash` makes every in-app link a full document navigation,
  // so the popover is torn down by the page change rather than closed.
  // Marking the current surface still matters: it is the one tile that
  // does nothing, and saying so beforehand is cheaper than a reload.
  const isCurrent = (path) => (path === '/' ? pathname === '/' : pathname.startsWith(path));

  return (
    <>
      <IconButton
        onClick={open}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-controls={isOpen ? popoverId : undefined}
        aria-label="Buka menu"
        sx={{ width: 44, height: 44, bgcolor: 'grey.200', color: 'text.primary' }}
      >
        <Iconify icon={isOpen ? 'carbon:close' : 'carbon:menu'} width={22} />
      </IconButton>

      <Popover
        id={popoverId}
        open={isOpen}
        onClose={close}
        anchorEl={anchorEl}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        slotProps={{
          paper: {
            sx: {
              mt: 1,
              p: 1.25,
              width: 276,
              borderRadius: 2.75,
              boxShadow: '0 20px 48px -12px rgba(11,13,14,0.4)',
            },
          },
        }}
      >
        <Box
          component="nav"
          aria-label="Menu utama"
          sx={{ display: 'grid', gap: 1, gridTemplateColumns: 'repeat(2, minmax(0, 1fr))' }}
        >
          {appMenuTiles.map((tile) => (
            <Tile key={tile.path} tile={tile} current={isCurrent(tile.path)} />
          ))}
        </Box>
      </Popover>
    </>
  );
}

// ----------------------------------------------------------------------

/**
 * One destination.
 *
 * 70px tall, so the whole tile clears the 44px touch minimum with room
 * for a label that does not abbreviate. `accent` is manual entry, kept
 * visually louder than the rest because it is the one tile that writes
 * something rather than navigating to a view.
 */
function Tile({ tile, current }) {
  return (
    <Box
      component={RouterLink}
      href={tile.path}
      aria-current={current ? 'page' : undefined}
      sx={{
        gap: 0.75,
        height: 70,
        display: 'flex',
        borderRadius: 2,
        alignItems: 'center',
        flexDirection: 'column',
        textDecoration: 'none',
        justifyContent: 'center',
        color: 'text.primary',
        bgcolor: 'grey.100',
        ...(tile.accent && { color: 'primary.darker', bgcolor: 'primary.lighter' }),
        ...(current && { color: 'common.white', bgcolor: 'text.primary' }),
      }}
    >
      <Iconify icon={tile.icon} width={22} />
      <Box component="span" sx={{ fontSize: 12, fontWeight: 800 }}>
        {tile.label}
      </Box>
    </Box>
  );
}
