/**
 * Client-side state that belongs to one signed-in session.
 *
 * sessionStorage is scoped to the tab, not to the account, so anything
 * parked there outlives the person who put it in: sign out, hand the
 * phone over, sign in as someone else, and it is still there. The
 * backend goes to some length to make sure one owner never sees
 * another's rows (AC08); an unsent composer draft reappearing for the
 * next account is small by comparison, but it is the same kind of
 * leak, and it is ours to close.
 *
 * Every accessor is guarded because sessionStorage throws outright in
 * some private-browsing modes.
 */

/** The chat composer's unsent text, kept across navigation (FR17). */
export const CHAT_DRAFT_KEY = 'chat-composer-draft';

const SESSION_KEYS = [CHAT_DRAFT_KEY];

/** Wipes what this session left behind. Called on sign-out. */
export function clearSessionState() {
  SESSION_KEYS.forEach((key) => {
    try {
      sessionStorage.removeItem(key);
    } catch {
      // Nothing to recover: if it cannot be read it was never written.
    }
  });
}
