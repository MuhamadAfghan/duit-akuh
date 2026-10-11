// ----------------------------------------------------------------------

/**
 * How the chat says a time.
 *
 * Separate from `format-time.js`, which is the template's generic dayjs
 * helper set in English. These three are the chat's own vocabulary and
 * they are pinned to one zone on purpose.
 *
 * **Everything is rendered in Asia/Jakarta, not the device's zone.** The
 * PRD fixes the product's timezone, and the ledger's day boundaries are
 * Jakarta's: a transaction written at 23.30 WIB belongs to that day even
 * if the phone is in Singapore. A bubble that said "00.30, besok" while
 * the summary counted it as today would be the app contradicting itself.
 *
 * Native `Intl` rather than dayjs's utc+timezone plugins: those are two
 * more imports for what one formatter already does, and nothing here
 * needs date arithmetic.
 */

const ZONE = 'Asia/Jakarta';

/** 09.02 — Indonesian writes a dot between hour and minute, not a colon. */
const timeFormat = new Intl.DateTimeFormat('id-ID', {
  hour: '2-digit',
  minute: '2-digit',
  timeZone: ZONE,
});

/** 2026-10-11. `en-CA` is the shortest way to get an ISO-shaped date. */
const dayKeyFormat = new Intl.DateTimeFormat('en-CA', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  timeZone: ZONE,
});

/** 9 Okt — the separator for anything older than yesterday. */
const dayLabelFormat = new Intl.DateTimeFormat('id-ID', {
  day: 'numeric',
  month: 'short',
  timeZone: ZONE,
});

/**
 * Parses whatever the API handed us.
 *
 * Returns null rather than an Invalid Date, because every caller here
 * renders into the thread: a bubble missing its timestamp is a small
 * loss, a thread that throws is the whole screen.
 */
function toDate(value) {
  if (!value) {
    return null;
  }

  const date = value instanceof Date ? value : new Date(value);

  return Number.isNaN(date.getTime()) ? null : date;
}

// ----------------------------------------------------------------------

/** The time inside a bubble. `09.02`, or null if there is nothing to say. */
export function fChatTime(value) {
  const date = toDate(value);

  return date ? timeFormat.format(date) : null;
}

/**
 * The Jakarta calendar day, as a comparable string.
 *
 * This is what groups bubbles under a separator. It must come from the
 * same zone as the label, or a message would sit under the wrong date
 * for the few hours the two zones disagree.
 */
export function chatDayKey(value) {
  const date = toDate(value);

  return date ? dayKeyFormat.format(date) : null;
}

/**
 * The day separator's text: `HARI INI`, `KEMARIN`, or `9 OKT`.
 *
 * Relative to now, so it has to be called at render time rather than
 * memoised across a day boundary — which is also why the thread passes
 * the raw value down instead of a precomputed label.
 */
export function fChatDay(value) {
  const key = chatDayKey(value);

  if (!key) {
    return null;
  }

  const now = Date.now();

  if (key === dayKeyFormat.format(new Date(now))) {
    return 'HARI INI';
  }

  if (key === dayKeyFormat.format(new Date(now - 86_400_000))) {
    return 'KEMARIN';
  }

  return dayLabelFormat.format(toDate(value)).toUpperCase();
}
