import { CONFIG } from 'src/global-config';

import { CheckEmailView } from 'src/auth/view/session';

// ----------------------------------------------------------------------

export const metadata = { title: `Cek email - ${CONFIG.appName}` };

export default function Page() {
  return <CheckEmailView />;
}
