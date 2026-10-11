// ----------------------------------------------------------------------

const ROOTS = {
  AUTH: '/auth',
  DASHBOARD: '/dashboard',
};

// ----------------------------------------------------------------------

export const paths = {
  /**
   * The app surfaces (PRD FR17 bottom tabs). Chat is the root: it is
   * the main surface, not a sub-page (FR14).
   */
  chat: '/',
  ringkasan: '/ringkasan',
  saya: '/saya',
  faqs: '/faqs',
  minimalStore: 'https://mui.com/store/items/minimal-dashboard/',
  /**
   * Surfaces reached from Ringkasan or the tab bar. Everything here can
   * also be done in chat (FR14); these exist because a list is a better
   * way to read ten wallets than a sentence is.
   */
  data: '/data',
  catat: '/catat',
  kantong: '/kantong',
  budget: '/budget',
  target: '/target',
  simulasi: '/simulasi',
  // AUTH
  auth: {
    signIn: `${ROOTS.AUTH}/sign-in`,
    signUp: `${ROOTS.AUTH}/sign-up`,
    forgot: `${ROOTS.AUTH}/lupa`,
    checkEmail: `${ROOTS.AUTH}/cek-email`,
    reset: `${ROOTS.AUTH}/reset`,
  },
  // DASHBOARD
  dashboard: {
    root: ROOTS.DASHBOARD,
    two: `${ROOTS.DASHBOARD}/two`,
    three: `${ROOTS.DASHBOARD}/three`,
    group: {
      root: `${ROOTS.DASHBOARD}/group`,
      five: `${ROOTS.DASHBOARD}/group/five`,
      six: `${ROOTS.DASHBOARD}/group/six`,
    },
  },
};
