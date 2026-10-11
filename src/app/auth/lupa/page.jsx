import { CONFIG } from 'src/global-config';

import { ForgotPasswordView } from 'src/auth/view/session';

// ----------------------------------------------------------------------

export const metadata = { title: `Lupa kata sandi - ${CONFIG.appName}` };

export default function Page() {
  return <ForgotPasswordView />;
}
