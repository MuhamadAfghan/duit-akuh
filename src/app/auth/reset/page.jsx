import { CONFIG } from 'src/global-config';

import { ResetPasswordView } from 'src/auth/view/session';

// ----------------------------------------------------------------------

export const metadata = { title: `Kata sandi baru - ${CONFIG.appName}` };

export default function Page() {
  return <ResetPasswordView />;
}
