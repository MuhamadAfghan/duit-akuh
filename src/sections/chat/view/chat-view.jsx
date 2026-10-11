'use client';

import { useRef, useState, useEffect, useCallback } from 'react';

import Box from '@mui/material/Box';

import { chatApi, ApiError, accountsApi } from 'src/lib/api';

import { DraftCard } from '../cards';
import { ChatHeader } from '../chat-header';
import { ChatThread } from '../chat-thread';
import { ChatComposer } from '../chat-composer';
import { WalletSuggestions, FIRST_RUN_GREETING } from '../first-run';

// ----------------------------------------------------------------------

const WELCOME = {
  id: 'welcome',
  role: 'assistant',
  body:
    'Halo! Catat pengeluaran, buat kantong, atau tanya posisi uangmu — semuanya dari sini.\n\n' +
    'Coba: "kemarin makan 35rb pakai BCA"',
};

/**
 * The in-progress assistant turn. A fixed id so each token replaces the
 * same bubble instead of appending a new one.
 */
const STREAMING_ID = 'streaming';

/** What to show while a tool runs, so the pause has a reason. */
const TOOL_STATUS = {
  get_accounts: 'Melihat kantong…',
  get_summary: 'Menghitung saldo…',
  get_spending: 'Menghitung pengeluaran…',
  get_budgets: 'Memeriksa budget…',
  get_goals: 'Memeriksa target…',
  find_transactions: 'Mencari transaksi…',
  run_simulation: 'Menghitung simulasi…',
  propose_transactions: 'Menyusun draft…',
  propose_account_change: 'Menyusun kantong baru…',
  propose_correction: 'Menyusun pembatalan…',
  propose_goal: 'Menyusun target…',
  propose_allocation: 'Menyusun alokasi…',
  propose_budget: 'Menyusun budget…',
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

// ----------------------------------------------------------------------

export function ChatView() {
  const [messages, setMessages] = useState([WELCOME]);
  const [sending, setSending] = useState(false);
  const [status, setStatus] = useState('');
  const [accountNames, setAccountNames] = useState({});
  //: null until the wallet list has actually been read. "Not loaded yet"
  //: and "none at all" lead to different screens, so they cannot share
  //: a value.
  const [walletCount, setWalletCount] = useState(null);
  const [freeToSpend, setFreeToSpend] = useState(null);
  const [prefill, setPrefill] = useState(null);

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
      .then((rows) => {
        setAccountNames(Object.fromEntries(rows.map((a) => [a.id, a.name])));
        setWalletCount(rows.length);
      })
      .catch(() => {});
  }, [messages]);

  // The one number the whole app exists to produce, kept in view while
  // you type. Re-read after every turn because a confirmed draft moves
  // it. A failure just hides the chip: it is context, not content.
  useEffect(() => {
    accountsApi
      .summary()
      .then((data) => {
        const value = data?.free_to_spend;
        // formatRupiah throws on a non-integer by design, which is
        // right for a card but wrong for a header chip: it would take
        // the whole thread down over a decoration.
        if (Number.isInteger(value)) {
          setFreeToSpend(value);
          return;
        }
        if (value != null) {
          console.error('free_to_spend bukan bilangan bulat:', value);
        }
        setFreeToSpend(null);
      })
      .catch(() => setFreeToSpend(null));
  }, [messages]);

  const handleSend = useCallback(
    async (body) => {
      // Shown immediately so the thread feels responsive; the reload
      // below replaces it with the server's own row.
      const optimistic = { id: nextLocalId(), role: 'user', body };
      setMessages((prev) => [...prev, optimistic]);
      setSending(true);
      setStatus('Menghubungi AI…');

      try {
        // Streamed so the thread shows progress instead of a blank
        // wait: tool names explain the pause, and the reply types out.
        let streamed = '';

        await chatApi.stream(body, (event) => {
          if (event.type === 'tool') {
            setStatus(TOOL_STATUS[event.name] ?? 'Memeriksa data…');
            return;
          }

          if (event.type === 'reset') {
            // What was streamed turned out to be the model narrating a
            // plan, not answering. Drop it rather than leave a bubble
            // claiming something happened before it did.
            streamed = '';
            setMessages((prev) => prev.filter((m) => m.id !== STREAMING_ID));
            return;
          }

          if (event.type === 'token') {
            streamed += event.text;
            setStatus('');
            setMessages((prev) => {
              const rest = prev.filter((m) => m.id !== STREAMING_ID);
              return [...rest, { id: STREAMING_ID, role: 'assistant', body: streamed }];
            });
            return;
          }

          if (event.type === 'error') {
            setMessages((prev) => [
              ...prev.filter((m) => m.id !== STREAMING_ID),
              { id: nextLocalId(), role: 'assistant', body: event.message },
            ]);
          }
        });

        // Replace the optimistic and streamed placeholders with the
        // server's own rows, which carry the real ids and any cards.
        await reload();
      } catch (error) {
        // Each of these is a different thing the user can do next, so
        // they are not collapsed into one "failed" message.
        const BY_CODE = {
          offline: 'Tidak ada koneksi. Pesan belum terkirim dan tidak ada yang tersimpan.',
          ai_rate_limited:
            'Terlalu banyak pesan dalam waktu singkat. Tunggu sebentar, lalu coba lagi.',
          ai_busy:
            'Layanan AI sedang penuh. Coba lagi sebentar lagi, atau catat manual lewat halaman Data.',
          already_processing: 'Pesan sebelumnya masih diproses. Tunggu sebentar.',
        };

        const message =
          (error instanceof ApiError && BY_CODE[error.code]) || 'Gagal mengirim pesan. Coba lagi.';

        setMessages((prev) => [...prev, { id: nextLocalId(), role: 'assistant', body: message }]);
        setStatus('');
      } finally {
        setSending(false);
        setStatus('');
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
    (message) => (
      <DraftCard
        card={message.card}
        names={accountNames}
        onConfirm={() => handleConfirm(message.card)}
        onCancel={() => handleCancel(message.card)}
      />
    ),
    [handleConfirm, handleCancel, accountNames]
  );

  // No wallet exists yet, so the thread opens on board "Mulai": the
  // usual greeting offers to record spending from accounts that are not
  // there. `noWallet` stays true until one is saved — the header and
  // the placeholder keep saying what is missing — while the chips only
  // stand in for a first message, and go once one has been sent.
  const noWallet = walletCount === 0 && messages[0]?.id === WELCOME.id;
  const untouched = noWallet && messages.length === 1;

  const thread = noWallet ? [...FIRST_RUN_GREETING, ...messages.slice(1)] : messages;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', flex: '1 1 auto', minHeight: 0 }}>
      <ChatHeader
        status={status}
        freeToSpend={freeToSpend}
        hint={noWallet ? 'Kantong pertama' : null}
      />

      <ChatThread
        messages={thread}
        renderCard={renderCard}
        footer={
          untouched ? (
            <WalletSuggestions
              disabled={sending}
              onPick={(name) => setPrefill({ text: name, at: Date.now() })}
            />
          ) : null
        }
      />

      <ChatComposer
        onSend={handleSend}
        disabled={sending}
        prefill={prefill}
        suggestions={noWallet ? [] : undefined}
        placeholder={noWallet ? 'Kantong lain? Tulis di sini…' : undefined}
      />
    </Box>
  );
}
