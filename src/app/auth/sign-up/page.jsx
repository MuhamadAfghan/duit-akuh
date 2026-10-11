import { CONFIG } from 'src/global-config';

import { SignUpView } from 'src/auth/view/session';

// ----------------------------------------------------------------------

export const metadata = { title: `Daftar - ${CONFIG.appName}` };

export default function Page() {
  return <SignUpView />;
}
