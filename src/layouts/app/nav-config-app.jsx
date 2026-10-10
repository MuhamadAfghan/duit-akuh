import { paths } from 'src/routes/paths';

// ----------------------------------------------------------------------

/**
 * The three bottom tabs required by PRD FR17: Chat, Ringkasan, Data.
 *
 * Chat is first and is the root path because it is the primary surface
 * (FR14); the other two are companion views over the same data.
 *
 * Icons are picked from the set registered in
 * src/components/iconify/icon-sets.js so they render offline and do not
 * flicker — a plain Iconify name would be fetched from the network.
 */
export const appTabs = [
  {
    label: 'Chat',
    path: paths.chat,
    icon: 'solar:chat-round-dots-bold',
  },
  {
    label: 'Ringkasan',
    path: paths.ringkasan,
    icon: 'solar:wad-of-money-bold',
  },
  {
    label: 'Data',
    path: paths.data,
    icon: 'solar:bill-list-bold',
  },
];
