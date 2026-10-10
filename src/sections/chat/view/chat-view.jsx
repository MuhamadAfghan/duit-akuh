'use client';

import { useRef, useState, useCallback } from 'react';

import Box from '@mui/material/Box';

import { formatRupiah } from 'src/utils/format-money';

import { ChatHeader } from '../chat-header';
import { ChatThread } from '../chat-thread';
import { ChatComposer } from '../chat-composer';
import { TransactionDraftCard } from '../cards';
import { stubProposeTransaction } from '../stub-orchestrator';

// ----------------------------------------------------------------------

const INITIAL_MESSAGES = [
  {
    id: 'welcome',
    role: 'assistant',
    body:
      'Halo! Catat pengeluaran, buat kantong, atau tanya posisi uangmu — semuanya dari sini.\n\n' +
      'Coba: "kemarin makan 35rb pakai BCA"',
  },
];

let messageCounter = 0;
const nextId = () => {
  messageCounter += 1;
  return `m${messageCounter}`;
};

const formatTime = () =>
  new Intl.DateTimeFormat('id-ID', { hour: '2-digit', minute: '2-digit' }).format(new Date());

// ----------------------------------------------------------------------

/**
 * The single persistent conversation that is the app's main surface
 * (PRD FR14).
 *
 * State is local and backed by the stub orchestrator for now. When the
 * FastAPI backend lands, `handleSend` posts the message and `handleConfirm`
 * calls the confirmation endpoint; the shape here already matches that flow
 * (propose -> show impact -> confirm -> saved), so only the data source
 * changes.
 */
export function ChatView() {
  const [messages, setMessages] = useState(INITIAL_MESSAGES);

  /**
   * Operation IDs already submitted. The PRD requires a confirmation sent
   * twice to produce exactly one transaction (AC04), and a stale card
   * button not to create a duplicate (AC13). The real guard is the
   * backend's idempotency key; this stops the UI from firing twice at all.
   */
  const submittedRef = useRef(new Set());

  const updateCard = useCallback((id, patch) => {
    setMessages((prev) =>
      prev.map((message) =>
        message.id === id ? { ...message, card: { ...message.card, ...patch } } : message
      )
    );
  }, []);

  const handleSend = useCallback((body) => {
    const userMessage = { id: nextId(), role: 'user', body, time: formatTime() };
    const proposal = stubProposeTransaction(body);

    const reply = proposal
      ? {
          id: nextId(),
          role: 'assistant',
          card: {
            kind: 'transaction',
            status: 'draft',
            operationId: `op-${nextId()}`,
            ...proposal,
          },
        }
      : {
          id: nextId(),
          role: 'assistant',
          body:
            'Belum ada backend yang terhubung, jadi aku belum bisa menjawab itu. ' +
            'Sebutkan nominal (misal "35rb") untuk melihat kartu draft.',
        };

    setMessages((prev) => [...prev, userMessage, reply]);
  }, []);

  const handleConfirm = useCallback(
    (message) => {
      const { operationId, draft } = message.card;

      if (submittedRef.current.has(operationId)) {
        return;
      }

      submittedRef.current.add(operationId);
      updateCard(message.id, { status: 'saving' });

      // Stands in for the backend confirmation call.
      setTimeout(() => {
        updateCard(message.id, {
          status: 'saved',
          // FR05: a success reply names the amount, date, account and
          // category, and links to the detail.
          statusMessage:
            `Tersimpan: ${formatRupiah(draft.amount)} · ${draft.date} · ` +
            `${draft.from} · ${draft.category}`,
        });
      }, 700);
    },
    [updateCard]
  );

  const handleCancel = useCallback(
    (message) => {
      updateCard(message.id, {
        status: 'cancelled',
        statusMessage: 'Draft dibatalkan. Tidak ada yang tersimpan.',
      });
    },
    [updateCard]
  );

  const renderCard = useCallback(
    (message) => (
      <TransactionDraftCard
        draft={message.card.draft}
        impact={message.card.impact}
        status={message.card.status}
        statusMessage={message.card.statusMessage}
        onConfirm={() => handleConfirm(message)}
        onCancel={() => handleCancel(message)}
      />
    ),
    [handleConfirm, handleCancel]
  );

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', flex: '1 1 auto', minHeight: 0 }}>
      <ChatHeader />
      <ChatThread messages={messages} renderCard={renderCard} />
      <ChatComposer onSend={handleSend} />
    </Box>
  );
}
