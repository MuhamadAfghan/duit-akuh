'use client';

import { useRef, useState, useEffect, useCallback } from 'react';

import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Button from '@mui/material/Button';

import { Iconify } from 'src/components/iconify';
import { Scrollbar } from 'src/components/scrollbar';

import { ChatMessage } from './chat-message';

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
export function ChatThread({ messages, renderCard }) {
  const scrollRef = useRef(null);
  const isStuckRef = useRef(true);

  const [showJump, setShowJump] = useState(false);

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
  }, [messages]);

  return (
    <Box sx={{ position: 'relative', flex: '1 1 auto', minHeight: 0, display: 'flex' }}>
      <Scrollbar ref={scrollRef} onScroll={handleScroll} sx={{ px: 2, py: 2 }}>
        <Stack spacing={1.5} sx={{ justifyContent: 'flex-end', flex: '1 1 auto' }}>
          {messages.map((message) =>
            message.card ? (
              <Box key={message.id} sx={{ display: 'flex', py: 0.5 }}>
                {renderCard(message)}
              </Box>
            ) : (
              <ChatMessage
                key={message.id}
                role={message.role}
                body={message.body}
                time={message.time}
              />
            )
          )}
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
