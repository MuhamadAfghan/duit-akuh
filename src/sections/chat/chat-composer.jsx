'use client';

import { useRef, useState, useEffect, useCallback } from 'react';

import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import InputBase from '@mui/material/InputBase';
import IconButton from '@mui/material/IconButton';

import { CHAT_DRAFT_KEY } from 'src/lib/session-state';

import { Iconify } from 'src/components/iconify';

import { ChatQuote } from './chat-quote';

// ----------------------------------------------------------------------

/** Sent as-is when tapped, so a first-time user has somewhere to start. */
const SUGGESTIONS = ['Saldo semua kantong', 'Sisa budget bulan ini', 'Uang bebas pakai berapa?'];

/**
 * Keeps the unsent message across navigation.
 *
 * The PRD is explicit that moving to another screen or opening a detail
 * panel must not lose a draft. sessionStorage is the right scope: it
 * survives tab switches and remounts, and stays on this device. It does
 * not expire with the account, though, so signing out clears it by hand
 * — see src/lib/session-state.js. Every access is guarded because it
 * throws in some private-browsing modes.
 */
function readDraft() {
  try {
    return sessionStorage.getItem(CHAT_DRAFT_KEY) ?? '';
  } catch {
    return '';
  }
}

function writeDraft(value) {
  try {
    if (value) {
      sessionStorage.setItem(CHAT_DRAFT_KEY, value);
    } else {
      sessionStorage.removeItem(CHAT_DRAFT_KEY);
    }
  } catch {
    // Not fatal: the draft simply will not survive a remount.
  }
}

// ----------------------------------------------------------------------

export function ChatComposer({
  onSend,
  onStop = null,
  replyTo = null,
  onCancelReply = null,
  disabled = false,
  suggestions = SUGGESTIONS,
  placeholder = 'Tulis atau tanya…',
  prefill = null,
}) {
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

  /**
   * Text handed over from elsewhere — a wallet chip in the first-run
   * thread, for instance. `prefill.at` is a timestamp rather than a
   * flag so picking the same chip twice still lands.
   */
  useEffect(() => {
    if (!prefill?.text) {
      return;
    }

    const next = `${prefill.text} `;

    setValue(next);
    writeDraft(next);
    inputRef.current?.focus();
  }, [prefill?.text, prefill?.at]);

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
      sx={{
        flexShrink: 0,
        pt: 1.25,
        bgcolor: 'background.paper',
        borderTop: '1px solid',
        borderColor: 'grey.200',
      }}
    >
      {/* What you are answering, kept in view while you type. Without
          it a reply picked three bubbles ago becomes a guess by the
          time the message is written. */}
      {replyTo && (
        <Box sx={{ px: 2, pb: 1.25, gap: 1, display: 'flex', alignItems: 'center' }}>
          <ChatQuote
            role={replyTo.role}
            excerpt={replyTo.excerpt}
            sx={{ flex: '1 1 auto', minWidth: 0 }}
          />

          <IconButton
            onClick={onCancelReply}
            aria-label="Batalkan balasan"
            sx={{ width: 36, height: 36, flexShrink: 0, bgcolor: 'grey.200' }}
          >
            <Iconify icon="carbon:close" width={17} />
          </IconButton>
        </Box>
      )}

      {/* Conversation starters. A chat-first app has to say what it can
          be asked, or the empty box is the hardest part of it. */}
      <Stack
        direction="row"
        sx={{ px: 2, pb: suggestions.length ? 1 : 0, gap: 1, overflowX: 'auto' }}
      >
        {suggestions.map((text) => (
          <Box
            key={text}
            component="button"
            type="button"
            disabled={disabled}
            onClick={() => onSend(text)}
            sx={{
              px: 1.75,
              height: 36,
              fontSize: 13,
              flexShrink: 0,
              fontWeight: 700,
              cursor: 'pointer',
              borderRadius: 999,
              border: '1.5px solid',
              borderColor: 'grey.300',
              color: 'text.primary',
              bgcolor: 'background.paper',
            }}
          >
            {text}
          </Box>
        ))}
      </Stack>

      <Box
        sx={{
          px: 2,
          gap: 1,
          display: 'flex',
          alignItems: 'flex-end',
          // Paper runs to the bottom edge, so the safe-area inset is
          // padding inside the composer rather than a gap under it.
          pb: 'calc(env(safe-area-inset-bottom) + 10px)',
        }}
      >
        <Box
          sx={{
            pl: 2,
            pr: 0.75,
            flex: '1 1 auto',
            minWidth: 0,
            display: 'flex',
            minHeight: 52,
            alignItems: 'center',
            borderRadius: 999,
            bgcolor: 'grey.100',
          }}
        >
          <InputBase
            multiline
            maxRows={5}
            value={value}
            inputRef={inputRef}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            inputProps={{ 'aria-label': 'Tulis pesan', enterKeyHint: 'send' }}
            sx={{
              flex: '1 1 auto',
              // 16px minimum: anything smaller makes iOS Safari zoom the
              // page on focus, which FR17 forbids.
              '& .MuiInputBase-input': { fontSize: 16, fontWeight: 600, lineHeight: 1.5 },
            }}
          />

          <IconButton
            aria-label="Foto struk"
            sx={{ width: 40, height: 40, flexShrink: 0, color: 'text.secondary' }}
          >
            <Iconify icon="solar:camera-add-bold" width={21} />
          </IconButton>

          <IconButton
            aria-label="Rekam suara"
            sx={{ width: 40, height: 40, flexShrink: 0, color: 'text.secondary' }}
          >
            <Iconify icon="solar:microphone-bold" width={21} />
          </IconButton>
        </Box>

        {/* While a turn is in flight the same slot stops it. A disabled
            send button would leave no way out of a wait that can run to
            Cloudflare's 100s limit, and `lumi-ai` has no SLA to promise
            otherwise. Stopping ends the wait, not the turn: the server
            finishes and the thread reloads to whatever it recorded. */}
        {disabled && onStop ? (
          <IconButton
            onClick={onStop}
            aria-label="Berhenti nunggu jawaban"
            sx={{ width: 52, height: 52, flexShrink: 0, bgcolor: 'text.primary' }}
          >
            <Box sx={{ width: 15, height: 15, borderRadius: '4px', bgcolor: 'common.white' }} />
          </IconButton>
        ) : (
          <IconButton
            disabled={!canSend}
            onClick={handleSend}
            aria-label="Kirim"
            sx={{
              width: 52,
              height: 52,
              flexShrink: 0,
              color: 'primary.contrastText',
              bgcolor: 'primary.main',
              '&:hover': { bgcolor: 'primary.dark' },
              '&.Mui-disabled': { color: 'grey.400', bgcolor: 'grey.200' },
            }}
          >
            <Iconify icon="lega:arrow-right" width={23} />
          </IconButton>
        )}
      </Box>
    </Box>
  );
}
