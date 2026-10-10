'use client';

import { useRef, useState, useEffect, useCallback } from 'react';

import Box from '@mui/material/Box';

import { chatApi, ApiError, accountsApi } from 'src/lib/api';

import { ChatHeader } from '../chat-header';
import { ChatThread } from '../chat-thread';
import { ChatComposer } from '../chat-composer';
import { TransactionDraftCard } from '../cards';

// ----------------------------------------------------------------------

const WELCOME = {
  id: 'welcome',
  role: 'assistant',
  body:
    'Halo! Catat pengeluaran, buat kantong, atau tanya posisi uangmu — semuanya dari sini.\n\n' +
    'Coba: "kemarin makan 35rb pakai BCA"',
};

let localId = 0;
const nextLocalId = () => {
  localId += 1;
  return `local-${localId}`;
};

/**
 * Turns the backend's message rows into what ChatThread renders.
 *
 * A row is either prose or a card; the card's figures come from the
 * stored draft, never recomputed here — the backend already decided
 * what the user was shown.
 */
function toThread(messages) {
  return messages.map((message) => {
    if (!message.draft) {
      return { id: message.id, role: message.role, body: message.body };
    }

    return {
      id: message.id,
      role: 'assistant',
      card: {
        draftId: message.draft.id,
        kind: message.draft.kind,
        status: message.draft.status,
        payload: message.draft.payload,
        impact: message.draft.impact ?? [],
      },
    };
  });
}

/**
 * Map a stored draft payload onto the card's display fields.
 *
 * The payload identifies accounts by id, so `names` maps them back for
 * display. Falls back to omitting the row rather than showing a UUID.
 */
function toCardDraft(card, names) {
  const { payload } = card;

  return {
    type: payload.type ?? card.kind,
    amount: payload.amount ?? 0,
    from: names[payload.from_account_id],
    to: names[payload.to_account_id] ?? names[payload.card_account_id],
    category: payload.category,
    merchant: payload.merchant,
    note: payload.note,
    fee: payload.fee,
    date: payload.occurred_at ? payload.occurred_at.slice(0, 10) : 'Hari ini',
  };
}

/** Card statuses the backend uses, mapped to what ActionCard expects. */
const CARD_STATUS = {
  pending: 'draft',
  confirmed: 'saved',
  cancelled: 'cancelled',
  stale: 'error',
};

// ----------------------------------------------------------------------

export function ChatView() {
  const [messages, setMessages] = useState([WELCOME]);
  const [sending, setSending] = useState(false);
  const [status, setStatus] = useState('');
  const [accountNames, setAccountNames] = useState({});

  // Guards against a double tap firing two confirmations before the
  // first response lands. The backend is idempotent regardless; this
  // just avoids a pointless second request.
  const busyDrafts = useRef(new Set());

  const reload = useCallback(async () => {
    try {
      const rows = await chatApi.messages();
      setMessages(rows.length ? toThread(rows) : [WELCOME]);
      setStatus('');
    } catch (error) {
      if (error instanceof ApiError && error.isUnauthorized) {
        setStatus('Belum masuk');
        return;
      }
      setStatus('Tidak tersambung');
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  // Account names are only needed to label card rows, so a failure here
  // degrades the card slightly rather than breaking the thread.
  useEffect(() => {
    accountsApi
      .list()
      .then((rows) => setAccountNames(Object.fromEntries(rows.map((a) => [a.id, a.name]))))
      .catch(() => {});
  }, [messages]);

  const handleSend = useCallback(
    async (body) => {
      // Shown immediately so the thread feels responsive; the reload
      // below replaces it with the server's own row.
      const optimistic = { id: nextLocalId(), role: 'user', body };
      setMessages((prev) => [...prev, optimistic]);
      setSending(true);
      setStatus('Mengetik…');

      try {
        await chatApi.send(body);
        await reload();
      } catch (error) {
        const message =
          error instanceof ApiError && error.isOffline
            ? 'Tidak ada koneksi. Pesan belum terkirim dan tidak ada yang tersimpan.'
            : 'Gagal mengirim pesan. Coba lagi.';

        setMessages((prev) => [...prev, { id: nextLocalId(), role: 'assistant', body: message }]);
        setStatus('');
      } finally {
        setSending(false);
      }
    },
    [reload]
  );

  const handleConfirm = useCallback(
    async (card) => {
      if (busyDrafts.current.has(card.draftId)) {
        return;
      }

      busyDrafts.current.add(card.draftId);

      setMessages((prev) =>
        prev.map((m) =>
          m.card?.draftId === card.draftId ? { ...m, card: { ...m.card, status: 'saving' } } : m
        )
      );

      try {
        await chatApi.confirmDraft(card.draftId);
      } catch {
        // Fall through to reload: the server's state is the truth about
        // whether anything was saved.
      } finally {
        busyDrafts.current.delete(card.draftId);
        await reload();
      }
    },
    [reload]
  );

  const handleCancel = useCallback(
    async (card) => {
      try {
        await chatApi.cancelDraft(card.draftId);
      } finally {
        await reload();
      }
    },
    [reload]
  );

  const renderCard = useCallback(
    (message) => {
      const { card } = message;
      // 'saving' is set locally and has no backend equivalent.
      const cardStatus =
        card.status === 'saving' ? 'saving' : (CARD_STATUS[card.status] ?? 'draft');

      return (
        <TransactionDraftCard
          draft={toCardDraft(card, accountNames)}
          impact={(card.impact ?? []).map((row) => ({
            label: row.account,
            before: row.before,
            after: row.after,
          }))}
          status={cardStatus}
          statusMessage={
            card.status === 'confirmed'
              ? 'Tersimpan.'
              : card.status === 'cancelled'
                ? 'Draft dibatalkan. Tidak ada yang tersimpan.'
                : card.status === 'stale'
                  ? 'Draft sudah tidak berlaku.'
                  : undefined
          }
          onConfirm={() => handleConfirm(card)}
          onCancel={() => handleCancel(card)}
        />
      );
    },
    [handleConfirm, handleCancel, accountNames]
  );

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', flex: '1 1 auto', minHeight: 0 }}>
      <ChatHeader status={status} />
      <ChatThread messages={messages} renderCard={renderCard} />
      <ChatComposer onSend={handleSend} disabled={sending} />
    </Box>
  );
}
