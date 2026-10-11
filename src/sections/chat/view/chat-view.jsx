'use client';

import { useRef, useMemo, useState, useEffect, useCallback } from 'react';

import Box from '@mui/material/Box';

import { chatApi, ApiError, accountsApi, conversationsApi } from 'src/lib/api';

import { ChatHeader } from '../chat-header';
import { ChatThread } from '../chat-thread';
import { ChatTyping } from '../chat-typing';
import { ChatSessions } from '../chat-sessions';
import { ChatComposer } from '../chat-composer';
import { DraftCard, DraftSheet } from '../cards';
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

/**
 * The same cut `_reply_out` makes in routes_chat.py.
 *
 * Two copies of one number, which buys an instant reply strip: the
 * quote shows the moment it is picked rather than after a round trip.
 * The server's own excerpt replaces this one on the next reload, so a
 * drift would show up as the quote changing under the cursor.
 */
const EXCERPT_CHARS = 160;

function excerptOf(body) {
  const flat = (body ?? '').replace(/\s+/g, ' ').trim();

  return flat.length > EXCERPT_CHARS ? `${flat.slice(0, EXCERPT_CHARS).trimEnd()}…` : flat;
}

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
      return {
        id: message.id,
        role: message.role,
        body: message.body,
        at: message.created_at,
        replyTo: message.reply_to ?? null,
        view: message.view ?? null,
        // Distinguishes a stored turn from the welcome text, the
        // first-run greeting and an optimistic bubble. Only a stored
        // turn has an id the server will accept as a reply target.
        saved: true,
      };
    }

    return {
      id: message.id,
      role: 'assistant',
      at: message.created_at,
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
  //: Connection trouble, shown in the header. Distinct from `stage`:
  //: one says the app cannot reach the server, the other says the
  //: assistant is working. They used to share a variable, which meant
  //: "Menghitung saldo…" and "Tidak tersambung" competed for one slot.
  const [status, setStatus] = useState('');
  //: What the assistant is doing right now, shown under the typing dots.
  const [stage, setStage] = useState('');
  //: The rows, not just the names: the revision form needs ids and
  //: types to draw a wallet picker, and deriving names from them keeps
  //: one source for both.
  const [accounts, setAccounts] = useState([]);
  //: null until the wallet list has actually been read. "Not loaded yet"
  //: and "none at all" lead to different screens, so they cannot share
  //: a value.
  const [walletCount, setWalletCount] = useState(null);
  const [freeToSpend, setFreeToSpend] = useState(null);
  const [prefill, setPrefill] = useState(null);
  //: Bumped whenever the ledger may have moved — i.e. after a completed
  //: turn or a decided draft. The wallet list and the free-to-spend
  //: chip watch this instead of `messages`: `messages` changes on every
  //: streamed token, so keying off it meant a full /accounts and
  //: /summary round trip *per token*. A couple of hundred tokens was a
  //: couple of hundred pairs of requests, which on a phone was enough
  //: to get the browser's renderer killed mid-reply.
  const [ledgerVersion, setLedgerVersion] = useState(0);
  //: Which draft the sheet is showing. Null means closed - including
  //: while a draft is still pending, because dismissing a sheet must
  //: not decide anything.
  const [sheetDraftId, setSheetDraftId] = useState(null);
  const [draftBusy, setDraftBusy] = useState(false);
  //: Why the last confirmation was refused. Cleared whenever the sheet
  //: moves on - a stale reason beside a fresh draft is worse than none.
  const [draftError, setDraftError] = useState(null);
  //: The turn the next message answers, as {id, role, excerpt}. Held
  //: here rather than in the composer because the thread is what picks
  //: it and the send is what consumes it.
  const [replyTo, setReplyTo] = useState(null);
  //: The thread on screen. Null only before the first load resolves it;
  //: the server always hands back one, creating it if the account has
  //: none, so there is no "no conversation" state to render.
  const [conversation, setConversation] = useState(null);
  const [threads, setThreads] = useState([]);
  const [sessionsOpen, setSessionsOpen] = useState(false);

  /**
   * Lets the person stop waiting.
   *
   * Aborting the fetch stops *this client reading*, not the server:
   * the turn keeps running upstream and is persisted like any other,
   * which is why the abort path reloads instead of keeping whatever
   * half-sentence was on screen. Nothing is lost and nothing is posted
   * - a draft still needs a confirmation either way.
   */
  const abortRef = useRef(null);

  // Guards against a double tap firing two confirmations before the
  // first response lands. The backend is idempotent regardless; this
  // just avoids a pointless second request.
  const busyDrafts = useRef(new Set());

  //: Drafts the user closed without deciding. Without this the effect
  //: below would reopen the sheet on the very next render.
  const dismissed = useRef(new Set());

  const refreshThreads = useCallback(async () => {
    try {
      const rows = await conversationsApi.list({ includeArchived: true });

      setThreads(rows);

      return rows;
    } catch {
      // The list is navigation, not content: a failure leaves the
      // current thread perfectly usable.
      return null;
    }
  }, []);

  /**
   * Which thread every call in here is about.
   *
   * A ref beside the state because `reload` is called from a dozen
   * places that have no business knowing about threads. Reading the id
   * from state would mean putting it in the dependency list of every
   * one of them, and a stale closure there would quietly reload the
   * wrong conversation after a switch.
   */
  const openThread = useRef(null);

  const reload = useCallback(async () => {
    try {
      const rows = await chatApi.messages(openThread.current);
      setMessages(rows.length ? toThread(rows) : [WELCOME]);
      setStatus('');
      // The ledger can only have moved when a turn has finished or a
      // draft was decided, and both end here. The wallet list and the
      // free-to-spend chip key off this rather than off `messages`,
      // which changes on every streamed token.
      setLedgerVersion((version) => version + 1);
    } catch (error) {
      if (error instanceof ApiError && error.isUnauthorized) {
        setStatus('Belum masuk');
        return;
      }
      setStatus('Tidak tersambung');
    }
  }, []);

  const openConversation = useCallback(
    async (next) => {
      openThread.current = next.id;
      setConversation(next);
      setSessionsOpen(false);
      // A reply and an unsent draft belong to the thread they were
      // picked in; carrying them across would quote a message that is
      // no longer on screen.
      setReplyTo(null);
      setMessages([WELCOME]);

      await reload();
    },
    [reload]
  );

  // The server resolves which thread to open - most recent, or a new
  // one - so the client never has to handle "no conversation yet".
  useEffect(() => {
    let cancelled = false;

    conversationsApi
      .active()
      .then((row) => {
        if (cancelled) {
          return;
        }

        openThread.current = row.id;
        setConversation(row);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) {
          reload();
        }
      });

    return () => {
      cancelled = true;
    };
  }, [reload]);

  // Account names are only needed to label card rows, so a failure here
  // degrades the card slightly rather than breaking the thread.
  useEffect(() => {
    accountsApi
      .list()
      .then((rows) => {
        setAccounts(rows);
        setWalletCount(rows.length);
      })
      .catch(() => {});
  }, [ledgerVersion]);

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
  }, [ledgerVersion]);

  const handleSend = useCallback(
    async (body) => {
      // Shown immediately so the thread feels responsive; the reload
      // below replaces it with the server's own row.
      const optimistic = {
        id: nextLocalId(),
        role: 'user',
        body,
        // Stamped here rather than left blank: the bubble is on screen
        // for a whole turn before the server's row replaces it, and a
        // bubble with no time would pop one in a second later.
        at: new Date().toISOString(),
        replyTo,
      };
      const replyToId = replyTo?.id ?? null;

      setMessages((prev) => [...prev, optimistic]);
      // Cleared on send, not on success: the strip describes the
      // message being written, and that message has left.
      setReplyTo(null);
      setSending(true);
      setStage('Menghubungi AI…');

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        // Streamed so the thread shows progress instead of a blank
        // wait: tool names explain the pause, and the reply types out.
        let streamed = '';

        await chatApi.stream(
          body,
          (event) => {
            if (event.type === 'tool') {
              setStage(TOOL_STATUS[event.name] ?? 'Memeriksa data…');
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
              setStage('');
              setMessages((prev) => {
                const rest = prev.filter((m) => m.id !== STREAMING_ID);
                return [
                  ...rest,
                  {
                    id: STREAMING_ID,
                    role: 'assistant',
                    body: streamed,
                    at: new Date().toISOString(),
                  },
                ];
              });
              return;
            }

            if (event.type === 'error') {
              setMessages((prev) => [
                ...prev.filter((m) => m.id !== STREAMING_ID),
                {
                  id: nextLocalId(),
                  role: 'assistant',
                  body: event.message,
                  at: new Date().toISOString(),
                },
              ]);
            }
          },
          { signal: controller.signal, replyToId, conversationId: openThread.current }
        );

        // Replace the optimistic and streamed placeholders with the
        // server's own rows, which carry the real ids and any cards.
        await reload();
        // The first message of a thread names it, so the header and the
        // list are both out of date until this lands.
        const rows = await refreshThreads();

        if (rows) {
          setConversation((current) => rows.find((thread) => thread.id === current?.id) ?? current);
        }
      } catch (error) {
        // Stopped on purpose. The turn itself was not cancelled, so the
        // server's rows - reply, draft, or nothing yet - are what the
        // thread should show, not the sentence that was cut mid-word.
        if (error.name === 'AbortError') {
          await reload();
          return;
        }

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

        setMessages((prev) => [
          ...prev,
          {
            id: nextLocalId(),
            role: 'assistant',
            body: message,
            at: new Date().toISOString(),
          },
        ]);
      } finally {
        abortRef.current = null;
        setSending(false);
        setStage('');
      }
    },
    [reload, refreshThreads, replyTo]
  );

  const handleReply = useCallback((message) => {
    setReplyTo({
      id: message.id,
      role: message.role,
      excerpt: excerptOf(message.body),
    });
  }, []);

  const handleNewChat = useCallback(async () => {
    const created = await conversationsApi.create();

    await openConversation(created);
    await refreshThreads();
  }, [openConversation, refreshThreads]);

  const handlePickThread = useCallback(
    async (id) => {
      const picked = threads.find((thread) => thread.id === id);

      await openConversation(picked ?? { id, title: null });
    },
    [threads, openConversation]
  );

  const handleUpdateThread = useCallback(
    async (id, patch) => {
      const updated = await conversationsApi.update(id, patch);

      await refreshThreads();

      // Renaming the thread you are in has to reach the header too.
      setConversation((current) => (current?.id === id ? updated : current));
    },
    [refreshThreads]
  );

  const handleStop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

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

      setDraftError(null);

      try {
        await chatApi.confirmDraft(card.draftId);
      } catch (error) {
        // A refused confirmation used to be swallowed here, which on a
        // sheet means the swipe simply does nothing - the one outcome a
        // money control must never have. The server is still the truth
        // about what was saved; this only says why it said no.
        setDraftError(error?.message ?? 'Gagal menyimpan. Coba lagi, atau cek saldo kantongnya.');
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

  const handleRevise = useCallback(
    async (patch, draftId) => {
      // The sheet passes the id of the card the patch was built from.
      // `sheetDraftId` is only a fallback: it tracks which sheet is open,
      // which is not always the same draft while a turn is streaming.
      const current = draftId ?? sheetDraftId;

      // Same guard as handleConfirm. Without it a second tap lands on a
      // draft the first tap has already had replaced server-side.
      if (!current || busyDrafts.current.has(current)) {
        return;
      }

      busyDrafts.current.add(current);
      setDraftBusy(true);

      try {
        const replacement = await chatApi.reviseDraft(current, patch);

        await reload();
        // The server cancelled `current` and handed back a new draft.
        // Point the sheet at it, or the next render finds nothing
        // pending under the old id and closes on a successful edit.
        setSheetDraftId(replacement.id);
      } catch (error) {
        // 404 means this draft is already gone — revised, confirmed or
        // cancelled. Re-syncing is the honest recovery: the sheet is
        // released so the pending-card effect can re-open it on whatever
        // is actually live. Surfacing "not found" instead left the sheet
        // pinned to a dead id, where every further tap failed the same
        // way — one stale card once became 57 refused posts.
        if (error?.status === 404) {
          await reload();
          setSheetDraftId(null);
          return;
        }

        throw error;
      } finally {
        busyDrafts.current.delete(current);
        setDraftBusy(false);
      }
    },
    [sheetDraftId, reload]
  );

  const accountNames = useMemo(
    () => Object.fromEntries(accounts.map((account) => [account.id, account.name])),
    [accounts]
  );

  const pendingCard = useMemo(
    () => messages.find((message) => message.card?.status === 'pending')?.card ?? null,
    [messages]
  );

  // A new draft opens its sheet by itself: the whole point of a
  // confirmation is that it is in front of you, not somewhere in the
  // scrollback. One the user has already waved away stays closed.
  useEffect(() => {
    if (pendingCard && !dismissed.current.has(pendingCard.draftId)) {
      setSheetDraftId(pendingCard.draftId);
    }
  }, [pendingCard]);

  const closeSheet = useCallback(() => {
    if (pendingCard) {
      dismissed.current.add(pendingCard.draftId);
    }

    setDraftError(null);
    setSheetDraftId(null);
  }, [pendingCard]);

  const renderCard = useCallback(
    (message) => (
      <DraftCard
        card={message.card}
        names={accountNames}
        accounts={accounts}
        onOpen={() => setSheetDraftId(message.card.draftId)}
        onConfirm={() => handleConfirm(message.card)}
        onCancel={() => handleCancel(message.card)}
      />
    ),
    [handleConfirm, handleCancel, accountNames, accounts]
  );

  // No wallet exists yet, so the thread opens on board "Mulai": the
  // usual greeting offers to record spending from accounts that are not
  // there. `noWallet` stays true until one is saved — the header and
  // the placeholder keep saying what is missing — while the chips only
  // stand in for a first message, and go once one has been sent.
  const noWallet = walletCount === 0 && messages[0]?.id === WELCOME.id;
  const untouched = noWallet && messages.length === 1;

  const thread = noWallet ? [...FIRST_RUN_GREETING, ...messages.slice(1)] : messages;

  // The dots stand in for the reply only until the first token lands.
  // After that the streaming bubble is itself the progress, and showing
  // both would claim two turns are coming.
  const isTyping = sending && !thread.some((message) => message.id === STREAMING_ID);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', flex: '1 1 auto', minHeight: 0 }}>
      <ChatHeader
        status={status}
        freeToSpend={freeToSpend}
        hint={noWallet ? 'Belum ada kantong' : null}
        title={conversation?.title ?? null}
        onNewChat={handleNewChat}
        onOpenSessions={() => {
          refreshThreads();
          setSessionsOpen(true);
        }}
      />

      <ChatSessions
        open={sessionsOpen}
        threads={threads}
        activeId={conversation?.id ?? null}
        busy={sending}
        onClose={() => setSessionsOpen(false)}
        onPick={handlePickThread}
        onCreate={handleNewChat}
        onUpdate={handleUpdateThread}
      />

      <ChatThread
        messages={thread}
        renderCard={renderCard}
        onReply={handleReply}
        footer={
          isTyping ? (
            <ChatTyping stage={stage} />
          ) : untouched ? (
            <WalletSuggestions
              disabled={sending}
              onPick={(name) => setPrefill({ text: name, at: Date.now() })}
            />
          ) : null
        }
      />

      <DraftSheet
        card={pendingCard}
        names={accountNames}
        accounts={accounts}
        saving={draftBusy}
        error={draftError}
        open={Boolean(pendingCard) && sheetDraftId === pendingCard?.draftId}
        onClose={closeSheet}
        onRevise={handleRevise}
        onConfirm={() => handleConfirm(pendingCard)}
        onCancel={() => handleCancel(pendingCard)}
      />

      <ChatComposer
        onSend={handleSend}
        onStop={handleStop}
        replyTo={replyTo}
        onCancelReply={() => setReplyTo(null)}
        disabled={sending}
        prefill={prefill}
        suggestions={noWallet ? [] : undefined}
        placeholder={noWallet ? 'Kantong lain? Tulis di sini…' : undefined}
      />
    </Box>
  );
}
