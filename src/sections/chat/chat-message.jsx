'use client';

import { varAlpha } from 'minimal-shared/utils';
import { useRef, useState, useCallback } from 'react';

import Box from '@mui/material/Box';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Typography from '@mui/material/Typography';
import IconButton from '@mui/material/IconButton';
import ListItemIcon from '@mui/material/ListItemIcon';

import { fChatDay, fChatTime } from 'src/utils/format-chat-time';

import { Iconify } from 'src/components/iconify';
import { Markdown } from 'src/components/markdown';

import { ChatQuote } from './chat-quote';

// ----------------------------------------------------------------------

/** Long enough not to fire on a tap, short enough not to feel stuck. */
const LONG_PRESS_MS = 450;

/**
 * One turn in the thread.
 *
 * `role` is 'user' or 'assistant'. Assistant turns may instead carry a card
 * (a draft, a summary), which ChatThread renders full width rather than as a
 * bubble, so this component only handles text.
 *
 * Both sides get a bubble, but not the same one. The person's is solid
 * ink; the assistant's is a white card on the grey canvas, the same
 * surface every other card in the app uses. That is the distinction
 * worth drawing — one side is speech, the other is the app answering —
 * and it is carried by surface rather than by two tinted colours facing
 * each other, which is what makes most chat UIs read as two strangers
 * talking.
 *
 * Giving the assistant a real surface also settles a layout problem:
 * a reply and a draft card used to sit on different grounds, so a turn
 * that was half sentence and half figures looked like two messages.
 */
export function ChatMessage({ role, body, at, replyTo, onReply }) {
  const isUser = role === 'user';

  const timer = useRef(null);
  const [anchorEl, setAnchorEl] = useState(null);

  const openMenu = useCallback((node) => setAnchorEl(node), []);
  const closeMenu = useCallback(() => setAnchorEl(null), []);

  const cancelPress = useCallback(() => {
    clearTimeout(timer.current);
    timer.current = null;
  }, []);

  const startPress = useCallback(
    (event) => {
      // Captured now: React resets currentTarget once the handler
      // returns, and this fires half a second later.
      const node = event.currentTarget;

      cancelPress();
      timer.current = setTimeout(() => openMenu(node), LONG_PRESS_MS);
    },
    [cancelPress, openMenu]
  );

  const handleContextMenu = useCallback(
    (event) => {
      // Desktop right-click, and the gesture iOS and Android already
      // raise for a long press on text.
      event.preventDefault();
      cancelPress();
      openMenu(event.currentTarget);
    },
    [cancelPress, openMenu]
  );

  const handleCopy = useCallback(async () => {
    closeMenu();

    try {
      await navigator.clipboard.writeText(body ?? '');
    } catch {
      // No clipboard permission, or an insecure origin. Nothing to
      // recover: the text is still on screen to select by hand.
    }
  }, [body, closeMenu]);

  const handleReply = useCallback(() => {
    closeMenu();
    onReply?.();
  }, [closeMenu, onReply]);

  const pressHandlers = {
    onPointerDown: startPress,
    onPointerUp: cancelPress,
    onPointerLeave: cancelPress,
    onPointerCancel: cancelPress,
    onContextMenu: handleContextMenu,
  };

  const menu = (
    <Menu
      open={Boolean(anchorEl)}
      anchorEl={anchorEl}
      onClose={closeMenu}
      anchorOrigin={{ vertical: 'bottom', horizontal: isUser ? 'right' : 'left' }}
      transformOrigin={{ vertical: 'top', horizontal: isUser ? 'right' : 'left' }}
      slotProps={{ paper: { sx: { minWidth: 184, borderRadius: 2.25 } } }}
    >
      {onReply && (
        <MenuItem onClick={handleReply} sx={{ minHeight: 48, fontWeight: 700 }}>
          <ListItemIcon>
            <Iconify icon="lega:back" width={20} />
          </ListItemIcon>
          Balas
        </MenuItem>
      )}

      <MenuItem onClick={handleCopy} sx={{ minHeight: 48, fontWeight: 700 }}>
        <ListItemIcon>
          <Iconify icon="solar:copy-bold" width={20} />
        </ListItemIcon>
        Salin teks
      </MenuItem>
    </Menu>
  );

  if (isUser) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}>
        <Box
          {...pressHandlers}
          sx={(theme) => ({
            px: 1.75,
            pt: 1.375,
            pb: 0.875,
            maxWidth: '85%',
            color: theme.vars.palette.common.white,
            bgcolor: theme.vars.palette.text.primary,
            borderRadius: '18px 18px 6px 18px',
          })}
        >
          {replyTo && (
            <ChatQuote
              onDark
              role={replyTo.role}
              excerpt={replyTo.excerpt}
              sx={{ mb: 1, maxWidth: 252 }}
            />
          )}

          {/* 16px minimum body text per FR17, and `pre-wrap` so a
              multi-line message keeps the shape it was typed in. */}
          <Typography
            variant="body1"
            sx={{ fontWeight: 600, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
          >
            {body}
          </Typography>

          <MetaRow time={fChatTime(at)} onDark onActions={onReply ? openMenu : null} />
        </Box>

        {menu}
      </Box>
    );
  }

  return (
    <Box sx={{ gap: 1, display: 'flex', alignItems: 'flex-end' }}>
      <AssistantMark />

      <Box
        {...pressHandlers}
        sx={(theme) => ({
          px: 1.75,
          pt: 1.375,
          pb: 0.875,
          maxWidth: '85%',
          bgcolor: theme.vars.palette.background.paper,
          borderRadius: '18px 18px 18px 6px',
          boxShadow: `0 1px 2px ${varAlpha(theme.vars.palette.grey['800Channel'], 0.07)}`,
        })}
      >
        {replyTo && (
          <ChatQuote role={replyTo.role} excerpt={replyTo.excerpt} sx={{ mb: 1, maxWidth: 240 }} />
        )}

        {/* The assistant writes Markdown whether or not anyone asked
            it to, so the bubble reads it. The person's own bubble does
            not: an asterisk somebody typed is an asterisk. */}
        <Markdown text={body} />

        <MetaRow time={fChatTime(at)} onActions={onReply ? openMenu : null} />
      </Box>

      {menu}
    </Box>
  );
}

// ----------------------------------------------------------------------

/**
 * The time, a tick on the person's own turns, and the way in to the
 * message's actions.
 *
 * Every bubble carries its own time rather than only the last of a run.
 * In a finance thread the timestamp is part of the record — "when did I
 * say I spent that" is a question people actually ask of this screen —
 * so it is content, not chrome, and hiding it to tidy a run of bubbles
 * would be hiding data.
 *
 * The tick means the server has the message, which is the only claim
 * the app can honestly make: there is nobody on the other end to read
 * it, so there is no second state to show.
 *
 * The dots are here, small and beside the metadata, rather than left to
 * the long press alone. A gesture with nothing on screen to suggest it
 * is a feature only the person who built it knows about.
 */
function MetaRow({ time, onDark = false, onActions }) {
  if (!time && !onActions) {
    return null;
  }

  const muted = (theme) =>
    onDark
      ? varAlpha(theme.vars.palette.common.whiteChannel, 0.76)
      : theme.vars.palette.text.secondary;

  return (
    <Box
      sx={{
        mt: 0.25,
        gap: 0.25,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'flex-end',
      }}
    >
      {time && (
        <Typography
          component="time"
          sx={(theme) => ({
            fontSize: 11,
            fontWeight: 700,
            fontVariantNumeric: 'tabular-nums',
            color: muted(theme),
          })}
        >
          {time}
        </Typography>
      )}

      {onDark && <Iconify width={14} icon="eva:checkmark-fill" sx={{ color: muted }} />}

      {onActions && (
        <IconButton
          size="small"
          aria-label="Aksi pesan"
          aria-haspopup="menu"
          onClick={(event) => onActions(event.currentTarget)}
          sx={{ ml: 0.25, mr: -0.75, width: 28, height: 28, color: muted }}
        >
          <Iconify width={17} icon="eva:more-horizontal-fill" />
        </IconButton>
      )}
    </Box>
  );
}

// ----------------------------------------------------------------------

/**
 * The band that separates one day from the next.
 *
 * ChatThread decides *where* one goes — it is the only place that can
 * see two messages at once — but the label is worked out here, at
 * render time, because "HARI INI" stops being true at midnight and the
 * thread's memo is keyed on messages, not on the clock.
 */
export function DaySeparator({ at }) {
  const label = fChatDay(at);

  if (!label) {
    return null;
  }

  return (
    <Box sx={{ pb: 0.25, display: 'flex', justifyContent: 'center' }}>
      <Box
        sx={{
          px: 1.5,
          py: 0.625,
          fontSize: 10,
          fontWeight: 800,
          borderRadius: 999,
          letterSpacing: '0.07em',
          color: 'text.secondary',
          bgcolor: 'grey.200',
        }}
      >
        {label}
      </Box>
    </Box>
  );
}

// ----------------------------------------------------------------------

/**
 * The dot that marks a machine turn.
 *
 * Same shape as the bubble in the logo, which is the whole idea: one
 * mark, used wherever the app speaks for itself.
 */
export function AssistantMark() {
  return (
    <Box
      aria-hidden
      sx={(theme) => ({
        mb: 0.25,
        width: 26,
        height: 26,
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
          width: 9,
          height: 9,
          borderRadius: '50%',
          bgcolor: theme.vars.palette.primary.main,
        })}
      />
    </Box>
  );
}
