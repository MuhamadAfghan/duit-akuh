'use client';

import { useRef, useMemo, Fragment, useState, useEffect, useCallback } from 'react';

import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Button from '@mui/material/Button';

import { chatDayKey } from 'src/utils/format-chat-time';

import { Iconify } from 'src/components/iconify';
import { Scrollbar } from 'src/components/scrollbar';

import { SpendingCard } from './cards/spending-card';
import { ChatMessage, DaySeparator } from './chat-message';

// ----------------------------------------------------------------------

/** How close to the bottom still counts as "following the conversation". */
const STICK_THRESHOLD = 80;

/**
 * The scrolling message area.
 *
 * Scroll behaviour is deliberate: new turns only pull the view down when
 * the user was already at the bottom. The PRD requires scroll position to
 * survive (section 12), so reading back through history must not be yanked
 * away when the assistant replies.
 *
 * When a turn arrives while the user is scrolled up, a jump button appears
 * instead — a confirmation card must never land silently off-screen.
 */
export function ChatThread({ messages, renderCard, onReply, footer = null }) {
  const scrollRef = useRef(null);
  const isStuckRef = useRef(true);

  const [showJump, setShowJump] = useState(false);

  /**
   * Which messages open a new day.
   *
   * Only the boundaries are worked out here; DaySeparator writes its own
   * label, because "HARI INI" expires at midnight and this memo does
   * not. Messages with no timestamp — the welcome text, a local error —
   * never open a day, so a thread that has only those shows no band at
   * all rather than one dated today.
   */
  const dayBreaks = useMemo(() => {
    const breaks = new Set();
    let previous = null;

    messages.forEach((message) => {
      const key = chatDayKey(message.at);

      if (key && key !== previous) {
        breaks.add(message.id);
        previous = key;
      }
    });

    return breaks;
  }, [messages]);

  const scrollToBottom = useCallback((behavior = 'smooth') => {
    const node = scrollRef.current;

    if (!node) {
      return;
    }

    node.scrollTo({ top: node.scrollHeight, behavior });
    isStuckRef.current = true;
    setShowJump(false);
  }, []);

  const handleScroll = useCallback(() => {
    const node = scrollRef.current;

    if (!node) {
      return;
    }

    const distance = node.scrollHeight - node.scrollTop - node.clientHeight;
    isStuckRef.current = distance <= STICK_THRESHOLD;

    if (isStuckRef.current) {
      setShowJump(false);
    }
  }, []);

  useEffect(() => {
    const node = scrollRef.current;

    if (!node) {
      return;
    }

    if (isStuckRef.current) {
      // 'auto' because this fires per new turn; smooth-scrolling every one
      // would queue animations and feel laggy.
      node.scrollTo({ top: node.scrollHeight, behavior: 'auto' });
    } else {
      setShowJump(true);
    }
  }, [messages, footer]);

  return (
    <Box sx={{ position: 'relative', flex: '1 1 auto', minHeight: 0, display: 'flex' }}>
      <Scrollbar ref={scrollRef} onScroll={handleScroll} sx={{ px: 2, py: 2 }}>
        <Stack spacing={1.5} sx={{ justifyContent: 'flex-end', flex: '1 1 auto' }}>
          {messages.map((message) => (
            <Fragment key={message.id}>
              {dayBreaks.has(message.id) && <DaySeparator at={message.at} />}

              {message.card ? (
                <Box sx={{ display: 'flex', py: 0.5 }}>{renderCard(message)}</Box>
              ) : (
                <>
                  <ChatMessage
                    role={message.role}
                    body={message.body}
                    at={message.at}
                    replyTo={message.replyTo}
                    // The welcome text, the first-run greeting and a
                    // message still in flight have no id the server
                    // would accept, so they get no actions at all — a
                    // "Balas" that 404s is worse than one not offered.
                    onReply={
                      onReply && message.saved && message.body ? () => onReply(message) : undefined
                    }
                  />

                  {/* Indented to the text column, so a breakdown reads
                      as part of what was just said rather than as a
                      second turn. 34px is the mark plus its gap. */}
                  {message.view?.kind === 'spending' && (
                    <Box sx={{ pl: '34px', pt: 0.75 }}>
                      <SpendingCard data={message.view.data} />
                    </Box>
                  )}
                </>
              )}
            </Fragment>
          ))}

          {footer}
        </Stack>
      </Scrollbar>

      {showJump && (
        <Button
          size="small"
          variant="contained"
          color="inherit"
          onClick={() => scrollToBottom()}
          startIcon={<Iconify icon="eva:arrow-ios-forward-fill" sx={{ rotate: '90deg' }} />}
          sx={{
            position: 'absolute',
            bottom: 12,
            left: '50%',
            translate: '-50%',
            minHeight: 44,
            boxShadow: 3,
          }}
        >
          Pesan baru
        </Button>
      )}
    </Box>
  );
}
