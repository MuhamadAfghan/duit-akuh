import { CONFIG } from 'src/global-config';

import { SignInView } from 'src/auth/view/session';

// ----------------------------------------------------------------------

export const metadata = { title: `Masuk - ${CONFIG.appName}` };

export default function Page() {
  return <SignInView />;
}
