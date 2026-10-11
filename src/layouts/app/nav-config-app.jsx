import { paths } from 'src/routes/paths';

// ----------------------------------------------------------------------

/**
 * The bottom tabs.
 *
 * PRD FR17 names three — Chat, Ringkasan, Data — and Kantong is a
 * fourth we added: it is the thing people open most, and reaching it
 * through Ringkasan put the app's most-used list two taps away for no
 * reason. Chat stays first and is the root path because it is the
 * primary surface (FR14); the rest are companion views over the same
 * data, and every one of them can also be driven from the chat.
 *
 * Saya took the slot Data used to hold. A signed-in app needs a way
 * out of itself, and for a while this one had none: the only sign-out
 * button lived in the template's dead /dashboard layout, so switching
 * accounts on a shared phone meant clearing a cookie by hand. Data did
 * not lose anything by moving — it is a tile in Ringkasan's menu, and
 * the same history is in the chat.
 *
 * Budget, Target and Simulasi deliberately stay off the bar. Five tabs
 * is where a bottom bar stops being scannable, and those three are
 * things you visit, not things you live in. They are one tap from
 * Ringkasan.
 *
 * **The bar does not appear on the chat.** Chat is the one surface that
 * needs its whole height — a composer, a keyboard and a thread — and it
 * carries `appMenuTiles` in its header instead. Every other surface
 * keeps the bar.
 *
 * Icons come from the set registered in
 * src/components/iconify/icon-sets.js so they render offline and do not
 * flicker — a plain Iconify name would be fetched from the network.
 */
export const appTabs = [
  {
    label: 'Chat',
    path: paths.chat,
    icon: 'lega:chat',
  },
  {
    label: 'Ringkasan',
    path: paths.ringkasan,
    icon: 'lega:chart',
  },
  {
    label: 'Kantong',
    path: paths.kantong,
    icon: 'lega:wallet',
  },
  {
    label: 'Saya',
    path: paths.saya,
    icon: 'lega:user',
  },
];

/**
 * The chat's menu, behind the button in its header.
 *
 * Eight tiles, because the chat has no tab bar to fall back on: this is
 * the only way off that screen, so it holds every destination at the
 * same depth rather than making Budget, Target and Simulasi hide behind
 * Ringkasan the way the bar does.
 *
 * There is no Chat tile — you are already there — and no sign-out.
 * Signing out lives in Saya behind a confirmation dialog, and copying
 * that flow into a dropdown would mean two places to keep in step, with
 * the riskier one a thumb's width under "Catat manual".
 *
 * Budget is `solar:chart-square-outline` and not `lega:chart`, here and
 * on Ringkasan's own tiles: Ringkasan owns the plain chart in the tab
 * bar, and in a two-column grid the two of them sat one above the other
 * wearing the same icon.
 */
export const appMenuTiles = [
  { label: 'Ringkasan', path: paths.ringkasan, icon: 'lega:chart' },
  { label: 'Kantong', path: paths.kantong, icon: 'lega:wallet' },
  { label: 'Budget', path: paths.budget, icon: 'solar:chart-square-outline' },
  { label: 'Target', path: paths.target, icon: 'lega:target' },
  { label: 'Simulasi', path: paths.simulasi, icon: 'lega:calculator' },
  { label: 'Data', path: paths.data, icon: 'lega:list' },
  { label: 'Saya', path: paths.saya, icon: 'lega:user' },
  { label: 'Catat manual', path: paths.catat, icon: 'lega:plus', accent: true },
];
