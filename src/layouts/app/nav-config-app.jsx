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
