// ----------------------------------------------------------------------

/**
 * PLACEHOLDER. Stands in for the chat orchestrator until the backend exists.
 *
 * In the real system (PRD section 5 and 13) a message goes:
 *
 *   PWA -> our FastAPI backend -> POST /v1/chat/completions on lumi-ai with
 *   the tool list -> `tool_calls` -> backend validates and computes the
 *   impact -> draft card.
 *
 * Nothing here is the intended implementation: the model must do the
 * interpreting, and the BACKEND must compute every balance. This file only
 * produces enough shape to exercise the UI states, and must be deleted when
 * the orchestrator lands. It is intentionally crude so it cannot be mistaken
 * for the real parser.
 */

/** Mock current balance, integer rupiah, standing in for backend state. */
const STUB_BALANCE = 5_000_000;

/**
 * Extremely rough amount reader: enough for "35rb" / "35 ribu" / "1,5 juta"
 * to demo the card. The real interpretation happens in the model.
 */
function readAmount(text) {
  const match = text.match(/(\d+(?:[.,]\d+)?)\s*(rb|ribu|jt|juta|k)?/i);

  if (!match) {
    return null;
  }

  const value = Number(match[1].replace(',', '.'));
  const unit = match[2]?.toLowerCase();

  const multiplier =
    unit === 'rb' || unit === 'ribu' || unit === 'k'
      ? 1_000
      : unit === 'jt' || unit === 'juta'
        ? 1_000_000
        : 1;

  // Money stays an integer (FR03).
  return Math.round(value * multiplier);
}

/**
 * Returns a draft plus its pre-computed impact, or null when nothing
 * resembling an amount was found.
 */
export function stubProposeTransaction(text) {
  const amount = readAmount(text);

  if (!amount) {
    return null;
  }

  const after = STUB_BALANCE - amount;

  return {
    draft: {
      type: 'expense',
      amount,
      from: 'BCA',
      category: 'Lain-lain',
      date: 'Hari ini',
      interpretation: `Dibaca dari: "${text}"`,
    },
    impact: [{ label: 'BCA', before: STUB_BALANCE, after }],
  };
}
