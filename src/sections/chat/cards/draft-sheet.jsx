'use client';

import { useState, useEffect } from 'react';

import Box from '@mui/material/Box';
import Drawer from '@mui/material/Drawer';

import { DraftCard } from './draft-card';
import { DraftRevise } from './draft-revise';

// ----------------------------------------------------------------------

/**
 * Kinds the server will accept a patch for.
 *
 * Mirrors `REVISABLE_KINDS` in `app/services/chat/revise.py`. Showing
 * "Ubah dulu" on a budget draft and then being refused would be worse
 * than not offering it, so the button is drawn from the same list —
 * but the server's copy is the one that decides.
 */
const REVISABLE = new Set(['expense', 'income', 'transfer', 'card_payment', 'refund']);

/** A batch is edited entry by entry, in the card, not in the form. */
const BATCH = 'batch';

// ----------------------------------------------------------------------

/**
 * Where a pending draft is decided.
 *
 * It used to be a card inline in the thread, which was fine for a
 * one-line expense and wrong for everything else: a draft you had to
 * scroll to find, and no room to edit it without the keyboard covering
 * the thing you were about to commit. A sheet owns the bottom of the
 * screen, so the amount, the impact and the swipe are in view together
 * and the editor has somewhere to open.
 *
 * Dismissing it does not decide anything. The draft stays pending and
 * the thread keeps a stub that opens this again — a confirmation must
 * never be lost by a stray swipe down, and it must never be committed
 * by one either.
 */
export function DraftSheet({
  card,
  names = {},
  accounts = [],
  open,
  saving = false,
  error: confirmError = null,
  onClose,
  onConfirm,
  onCancel,
  onRevise,
}) {
  const [mode, setMode] = useState('confirm');
  const [error, setError] = useState(null);

  // A revision replaces the draft, so the sheet is handed a different
  // card while it is open. Dropping back to the confirmation is the
  // point: the edit is done, and what needs checking now is the result.
  useEffect(() => {
    setMode('confirm');
    setError(null);
  }, [card?.draftId]);

  // The refusal belongs with the control that was refused.
  const shown = mode === 'revise' ? error : (error ?? confirmError);

  if (!card) {
    return null;
  }

  const handleApply = async (patch) => {
    setError(null);

    try {
      // The draft id travels with the patch on purpose. The patch is
      // built from *this* card's payload, so it has to be applied to
      // *this* card — the sheet's own id is tracked separately in the
      // view and the two can drift apart while a chat turn is streaming.
      await onRevise(patch, card.draftId);
    } catch (reason) {
      setError(reason?.message ?? 'Gagal mengubah draft. Coba lagi.');
    }
  };

  return (
    <Drawer
      anchor="bottom"
      open={open}
      onClose={onClose}
      slotProps={{
        paper: {
          sx: {
            mx: 'auto',
            width: 1,
            // The shell caps its column at 720; a drawer portals to the
            // body, so it has to be told the same thing or it spans a
            // desktop window the rest of the app never does.
            maxWidth: 720,
            maxHeight: '92dvh',
            overflowY: 'auto',
            borderRadius: '28px 28px 0 0',
            px: 2,
            pt: 1,
            pb: 'calc(env(safe-area-inset-bottom) + 16px)',
          },
        },
      }}
    >
      <Box
        aria-hidden
        sx={{ width: 38, height: 4, mx: 'auto', mb: 1.5, borderRadius: 1, bgcolor: 'grey.300' }}
      />

      {mode === 'revise' ? (
        <DraftRevise
          card={card}
          accounts={accounts}
          saving={saving}
          error={shown}
          onApply={handleApply}
          onBack={() => setMode('confirm')}
        />
      ) : (
        <>
          {shown && (
            <Box
              role="alert"
              sx={{
                mb: 1.25,
                px: 1.75,
                py: 1.25,
                fontSize: 13,
                fontWeight: 700,
                borderRadius: 2,
                color: 'error.darker',
                bgcolor: 'error.lighter',
              }}
            >
              {shown}
            </Box>
          )}

          <DraftCard
            card={{ ...card, status: saving ? 'saving' : card.status }}
            names={names}
            accounts={accounts}
            sheet
            onConfirm={onConfirm}
            onCancel={onCancel}
            // A batch has no single amount or wallet to edit, so it gets
            // no form: each entry is fixed where it sits, which is also
            // where the problem is visible.
            onRevise={REVISABLE.has(card.kind) ? () => setMode('revise') : undefined}
            onPatchItem={
              card.kind === BATCH
                ? (index, fields) => handleApply({ item: index, ...fields })
                : undefined
            }
          />
        </>
      )}
    </Drawer>
  );
}
