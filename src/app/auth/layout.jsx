import { AuthSplitLayout } from 'src/layouts/auth-split';

import { GuestGuard } from 'src/auth/guard';

// ----------------------------------------------------------------------

/**
 * Chrome and the guard for every auth screen.
 *
 * This used to be copied into each page's own layout, which is how the
 * five screens of the reset flow would have become five copies of the
 * same two wrappers — and how a sixth could quietly ship without a
 * guard at all.
 */
export default function Layout({ children }) {
  return (
    <GuestGuard>
      <AuthSplitLayout>{children}</AuthSplitLayout>
    </GuestGuard>
  );
}
