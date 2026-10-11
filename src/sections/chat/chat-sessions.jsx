'use client';

import { useMemo, useState, useCallback } from 'react';

import Box from '@mui/material/Box';
import Menu from '@mui/material/Menu';
import Stack from '@mui/material/Stack';
import Drawer from '@mui/material/Drawer';
import Dialog from '@mui/material/Dialog';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import InputBase from '@mui/material/InputBase';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import IconButton from '@mui/material/IconButton';
import DialogTitle from '@mui/material/DialogTitle';
import ListItemIcon from '@mui/material/ListItemIcon';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';

import { fChatTime, chatDayKey } from 'src/utils/format-chat-time';

import { Iconify } from 'src/components/iconify';
import { Scrollbar } from 'src/components/scrollbar';

// ----------------------------------------------------------------------

/** The server clips a title at 48; a person renaming one gets more. */
const TITLE_MAX = 96;

const dayFormat = new Intl.DateTimeFormat('id-ID', {
  day: 'numeric',
  month: 'short',
  timeZone: 'Asia/Jakarta',
});

/**
 * Which band a thread belongs under.
 *
 * Coarse on purpose. Finer buckets ("3 hari lalu") read as precision
 * the list does not have — what a person is actually scanning for is
 * roughly how long ago, and the row already carries the exact time.
 */
function bandOf(thread) {
  if (thread.is_pinned) {
    return 'DISEMATKAN';
  }

  const key = chatDayKey(thread.last_at);

  if (!key) {
    return 'BELUM ADA ISI';
  }

  const now = Date.now();
  const dayKey = (at) => chatDayKey(new Date(at).toISOString());

  if (key === dayKey(now)) {
    return 'HARI INI';
  }

  if (key === dayKey(now - 86_400_000)) {
    return 'KEMARIN';
  }

  return key >= dayKey(now - 7 * 86_400_000) ? '7 HARI TERAKHIR' : 'LEBIH LAMA';
}

/** The right-hand stamp: a time today, a date before that. */
function stampOf(thread) {
  if (!thread.last_at) {
    return null;
  }

  return bandOf(thread) === 'HARI INI'
    ? fChatTime(thread.last_at)
    : dayFormat.format(new Date(thread.last_at));
}

// ----------------------------------------------------------------------

/**
 * The list of threads, over the chat.
 *
 * A full-height drawer rather than a route. Every in-app link here is a
 * full document navigation (`trailingSlash`), so making this a page
 * would throw away the thread's scroll position and the composer's
 * unsent draft to show a list — and then throw them away again coming
 * back.
 *
 * There is no delete. Archiving takes a thread out of the list, which
 * is what the list is for; deleting one would destroy the only record
 * of why a transaction was entered, while the transaction itself would
 * outlive it.
 */
export function ChatSessions({
  open,
  threads,
  activeId,
  busy = false,
  onClose,
  onPick,
  onCreate,
  onUpdate,
}) {
  const [query, setQuery] = useState('');
  const [showArchived, setShowArchived] = useState(false);
  const [menu, setMenu] = useState(null);
  const [renaming, setRenaming] = useState(null);

  const closeMenu = useCallback(() => setMenu(null), []);

  const groups = useMemo(() => {
    const needle = query.trim().toLowerCase();

    const matching = threads.filter((thread) => {
      if (!showArchived && thread.is_archived) {
        return false;
      }

      if (!needle) {
        return true;
      }

      return `${thread.title ?? ''} ${thread.preview ?? ''}`.toLowerCase().includes(needle);
    });

    // The server already sorted: pinned first, then most recent. Bands
    // are read off that order rather than re-sorted, so the list cannot
    // disagree with itself about which thread is newest.
    const ordered = [];

    matching.forEach((thread) => {
      const band = bandOf(thread);
      const last = ordered[ordered.length - 1];

      if (last?.band === band) {
        last.threads.push(thread);
      } else {
        ordered.push({ band, threads: [thread] });
      }
    });

    return ordered;
  }, [threads, query, showArchived]);

  const handleRename = useCallback(
    async (title) => {
      const target = renaming;

      setRenaming(null);
      await onUpdate(target.id, { title });
    },
    [renaming, onUpdate]
  );

  return (
    <>
      <Drawer
        anchor="right"
        open={open}
        onClose={onClose}
        slotProps={{
          paper: {
            sx: { width: 1, maxWidth: 480, display: 'flex', flexDirection: 'column' },
          },
        }}
      >
        <Stack
          direction="row"
          sx={{
            px: 1.5,
            gap: 1,
            pb: 1.5,
            flexShrink: 0,
            alignItems: 'center',
            pt: 'calc(env(safe-area-inset-top) + 12px)',
          }}
        >
          <IconButton onClick={onClose} aria-label="Balik ke chat" sx={{ width: 44, height: 44 }}>
            <Iconify icon="lega:back" width={22} />
          </IconButton>

          <Typography
            component="h2"
            sx={{
              flexGrow: 1,
              minWidth: 0,
              fontSize: 19,
              fontWeight: 800,
              letterSpacing: '-0.02em',
            }}
          >
            Riwayat chat
          </Typography>

          <Button
            onClick={onCreate}
            disabled={busy}
            startIcon={<Iconify icon="lega:plus" width={18} />}
            sx={{
              px: 1.75,
              height: 44,
              fontWeight: 800,
              borderRadius: 999,
              color: 'common.white',
              bgcolor: 'text.primary',
              '&:hover': { bgcolor: 'grey.700' },
            }}
          >
            Baru
          </Button>
        </Stack>

        <Box sx={{ px: 1.75, pb: 1.5, flexShrink: 0 }}>
          <Stack
            direction="row"
            sx={{
              px: 1.75,
              gap: 1.25,
              height: 48,
              alignItems: 'center',
              borderRadius: 2,
              bgcolor: 'grey.100',
            }}
          >
            <Iconify icon="lega:search" width={19} sx={{ color: 'text.secondary' }} />
            <InputBase
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Cari judul atau isi chat…"
              inputProps={{ 'aria-label': 'Cari chat' }}
              sx={{ flex: '1 1 auto', '& .MuiInputBase-input': { fontSize: 16, fontWeight: 600 } }}
            />
          </Stack>
        </Box>

        <Scrollbar sx={{ flex: '1 1 auto', minHeight: 0, px: 1.75 }}>
          {groups.length === 0 && (
            <Typography
              sx={{
                py: 4,
                textAlign: 'center',
                fontSize: 14,
                fontWeight: 600,
                color: 'text.secondary',
              }}
            >
              {query ? 'Nggak ada chat yang cocok.' : 'Belum ada chat lain.'}
            </Typography>
          )}

          {groups.map((group) => (
            <Box key={group.band} sx={{ pb: 1 }}>
              <Typography
                sx={{
                  pl: 0.5,
                  pb: 0.75,
                  pt: 1.5,
                  fontSize: 10,
                  fontWeight: 800,
                  letterSpacing: '0.07em',
                  color: 'text.secondary',
                }}
              >
                {group.band}
              </Typography>

              {group.threads.map((thread) => (
                <ThreadRow
                  key={thread.id}
                  thread={thread}
                  active={thread.id === activeId}
                  onPick={() => onPick(thread.id)}
                  onMenu={(node) => setMenu({ node, thread })}
                />
              ))}
            </Box>
          ))}
        </Scrollbar>

        <Box
          sx={{ px: 1.75, flexShrink: 0, pb: 'calc(env(safe-area-inset-bottom) + 14px)', pt: 1 }}
        >
          <Button
            fullWidth
            onClick={() => setShowArchived((shown) => !shown)}
            sx={{ minHeight: 44, fontWeight: 800, color: 'text.secondary' }}
          >
            {showArchived ? 'Sembunyikan arsip' : 'Tampilkan arsip'}
          </Button>
        </Box>
      </Drawer>

      <Menu
        open={Boolean(menu)}
        anchorEl={menu?.node}
        onClose={closeMenu}
        slotProps={{ paper: { sx: { minWidth: 204, borderRadius: 2.25 } } }}
      >
        <MenuItem
          sx={{ minHeight: 48, fontWeight: 700 }}
          onClick={() => {
            setRenaming(menu.thread);
            closeMenu();
          }}
        >
          <ListItemIcon>
            <Iconify icon="solar:pen-bold" width={20} />
          </ListItemIcon>
          Ganti nama
        </MenuItem>

        <MenuItem
          sx={{ minHeight: 48, fontWeight: 700 }}
          onClick={() => {
            onUpdate(menu.thread.id, { is_pinned: !menu.thread.is_pinned });
            closeMenu();
          }}
        >
          <ListItemIcon>
            <Iconify icon="solar:flag-bold" width={20} />
          </ListItemIcon>
          {menu?.thread?.is_pinned ? 'Lepas sematan' : 'Sematkan'}
        </MenuItem>

        <MenuItem
          sx={{ minHeight: 48, fontWeight: 700 }}
          onClick={() => {
            onUpdate(menu.thread.id, { is_archived: !menu.thread.is_archived });
            closeMenu();
          }}
        >
          <ListItemIcon>
            <Iconify icon="solar:archive-down-minimlistic-bold" width={20} />
          </ListItemIcon>
          {menu?.thread?.is_archived ? 'Keluarkan dari arsip' : 'Arsipkan'}
        </MenuItem>
      </Menu>

      <RenameDialog thread={renaming} onClose={() => setRenaming(null)} onSubmit={handleRename} />
    </>
  );
}

// ----------------------------------------------------------------------

function ThreadRow({ thread, active, onPick, onMenu }) {
  const stamp = stampOf(thread);

  return (
    <Stack
      direction="row"
      sx={{
        pl: 1.5,
        pr: 0.75,
        gap: 0.5,
        py: 1.25,
        alignItems: 'center',
        borderRadius: 2.25,
        ...(active && { bgcolor: 'primary.lighter' }),
      }}
    >
      <Box
        component="button"
        type="button"
        onClick={onPick}
        aria-current={active ? 'true' : undefined}
        sx={{
          p: 0,
          border: 0,
          flex: '1 1 auto',
          minWidth: 0,
          textAlign: 'left',
          cursor: 'pointer',
          bgcolor: 'transparent',
        }}
      >
        <Stack direction="row" sx={{ gap: 0.75, alignItems: 'center', minWidth: 0 }}>
          {thread.is_pinned && (
            <Iconify
              icon="solar:flag-bold"
              width={13}
              sx={{ flexShrink: 0, color: active ? 'primary.dark' : 'text.secondary' }}
            />
          )}
          <Typography
            noWrap
            sx={{
              fontSize: 15,
              fontWeight: 800,
              color: active ? 'primary.darker' : 'text.primary',
            }}
          >
            {thread.title ?? 'Chat baru'}
          </Typography>
        </Stack>

        <Typography
          noWrap
          sx={{
            mt: 0.25,
            fontSize: 13,
            fontWeight: 600,
            color: active ? 'primary.dark' : 'text.secondary',
          }}
        >
          {thread.preview ?? 'Belum ada pesan'}
        </Typography>
      </Box>

      {stamp && (
        <Typography
          sx={{
            flexShrink: 0,
            fontSize: 11,
            fontWeight: 700,
            color: active ? 'primary.dark' : 'text.secondary',
          }}
        >
          {stamp}
        </Typography>
      )}

      <IconButton
        aria-label={`Aksi untuk ${thread.title ?? 'chat baru'}`}
        onClick={(event) => onMenu(event.currentTarget)}
        sx={{ width: 40, height: 40, flexShrink: 0 }}
      >
        <Iconify icon="eva:more-vertical-fill" width={18} />
      </IconButton>
    </Stack>
  );
}

// ----------------------------------------------------------------------

function RenameDialog({ thread, onClose, onSubmit }) {
  const [value, setValue] = useState('');

  // Keyed on the thread so the field is re-created with its name each
  // time one is opened, rather than kept from whichever was renamed
  // last.
  const key = thread?.id ?? 'none';

  return (
    <Dialog
      key={key}
      open={Boolean(thread)}
      onClose={onClose}
      fullWidth
      maxWidth="xs"
      slotProps={{ paper: { sx: { borderRadius: 3 } } }}
    >
      <DialogTitle sx={{ pb: 0.5, fontWeight: 800 }}>Ganti nama chat</DialogTitle>

      <DialogContent>
        <Typography sx={{ mb: 2, fontSize: 14, fontWeight: 600, color: 'text.secondary' }}>
          Kasih nama yang gampang lu cari lagi nanti. Ini cuma nama — nggak ngubah transaksi apa
          pun.
        </Typography>

        <TextField
          autoFocus
          fullWidth
          label="Nama chat"
          defaultValue={thread?.title ?? ''}
          onChange={(event) => setValue(event.target.value)}
          slotProps={{ htmlInput: { maxLength: TITLE_MAX } }}
        />
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 2.5 }}>
        <Button onClick={onClose} sx={{ minHeight: 44, fontWeight: 800, color: 'text.secondary' }}>
          Batal
        </Button>
        <Button
          onClick={() => onSubmit(value || thread?.title || '')}
          disabled={!(value || thread?.title || '').trim()}
          sx={{
            px: 2.5,
            minHeight: 44,
            fontWeight: 800,
            borderRadius: 999,
            color: 'common.white',
            bgcolor: 'text.primary',
            '&:hover': { bgcolor: 'grey.700' },
          }}
        >
          Simpan nama
        </Button>
      </DialogActions>
    </Dialog>
  );
}
