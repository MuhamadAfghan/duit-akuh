import { CONFIG } from 'src/global-config';
import { AppShell } from 'src/layouts/app';

import { AuthGuard } from 'src/auth/guard';

// ----------------------------------------------------------------------

/**
 * Shell for the three main surfaces (Chat, Ringkasan, Data).
 *
 * The guard is kept in place even while `CONFIG.auth.skip` is true during
 * the UI phase, so turning auth back on needs no structural change here.
 */
export default function Layout({ children }) {
  if (CONFIG.auth.skip) {
    return <AppShell>{children}</AppShell>;
  }

  return (
    <AuthGuard>
      <AppShell>{children}</AppShell>
    </AuthGuard>
  );
}
