'use client';

import { useRef, useState, useEffect, useCallback } from 'react';

import Box from '@mui/material/Box';
import InputBase from '@mui/material/InputBase';
import IconButton from '@mui/material/IconButton';

import { Iconify } from 'src/components/iconify';

// ----------------------------------------------------------------------

const DRAFT_STORAGE_KEY = 'chat-composer-draft';

/**
 * Keeps the unsent message across navigation.
 *
 * The PRD is explicit that moving to another screen or opening a detail
 * panel must not lose a draft. sessionStorage is the right scope: it
 * survives tab switches and remounts, stays on this device, and goes away
 * with the session. Every access is guarded because it throws in some
 * private-browsing modes.
 */
function readDraft() {
  try {
    return sessionStorage.getItem(DRAFT_STORAGE_KEY) ?? '';
  } catch {
    return '';
  }
}

function writeDraft(value) {
  try {
    if (value) {
      sessionStorage.setItem(DRAFT_STORAGE_KEY, value);
    } else {
      sessionStorage.removeItem(DRAFT_STORAGE_KEY);
    }
  } catch {
    // Not fatal: the draft simply will not survive a remount.
  }
}

// ----------------------------------------------------------------------

export function ChatComposer({ onSend, disabled = false }) {
  const inputRef = useRef(null);
  const [value, setValue] = useState('');

  // Restored after mount rather than via useState's initialiser, so the
  // server and first client render agree and hydration stays clean.
  useEffect(() => {
    const saved = readDraft();

    if (saved) {
      setValue(saved);
    }
  }, []);

  const handleChange = useCallback((event) => {
    setValue(event.target.value);
    writeDraft(event.target.value);
  }, []);

  const handleSend = useCallback(() => {
    const body = value.trim();

    if (!body || disabled) {
      return;
    }

    onSend(body);
    setValue('');
    writeDraft('');
  }, [value, disabled, onSend]);

  const handleKeyDown = useCallback(
    (event) => {
      // Shift+Enter keeps the newline; plain Enter sends.
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  const canSend = Boolean(value.trim()) && !disabled;

  return (
    <Box
      sx={(theme) => ({
        flexShrink: 0,
        px: 1.5,
        py: 1.25,
        display: 'flex',
        alignItems: 'flex-end',
        gap: 1,
        bgcolor: theme.vars.palette.background.paper,
        borderTop: `solid 1px ${theme.vars.palette.divider}`,
      })}
    >
      <InputBase
        multiline
        maxRows={5}
        value={value}
        inputRef={inputRef}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        placeholder="Catat transaksi atau tanya apa saja"
        // Hints the soft keyboard to show a send affordance.
        inputProps={{ 'aria-label': 'Tulis pesan', enterKeyHint: 'send' }}
        sx={(theme) => ({
          flex: '1 1 auto',
          px: 1.75,
          py: 1,
          borderRadius: 2.5,
          bgcolor: theme.vars.palette.background.neutral,
          // 16px minimum: anything smaller makes iOS Safari zoom the page
          // on focus, which FR17 forbids.
          '& .MuiInputBase-input': { fontSize: 16, lineHeight: 1.5 },
        })}
      />

      <IconButton
        color="primary"
        disabled={!canSend}
        onClick={handleSend}
        aria-label="Kirim"
        sx={(theme) => ({
          width: 44,
          height: 44,
          flexShrink: 0,
          color: theme.vars.palette.primary.contrastText,
          bgcolor: theme.vars.palette.primary.main,
          '&:hover': { bgcolor: theme.vars.palette.primary.dark },
          '&.Mui-disabled': {
            color: theme.vars.palette.action.disabled,
            bgcolor: theme.vars.palette.action.disabledBackground,
          },
        })}
      >
        <Iconify icon="solar:forward-bold" width={22} />
      </IconButton>
    </Box>
  );
}
