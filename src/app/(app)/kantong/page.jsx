import { CONFIG } from 'src/global-config';

import { KantongView } from 'src/sections/kantong';

// ----------------------------------------------------------------------

export const metadata = { title: `Kantong - ${CONFIG.appName}` };

export default function Page() {
  return <KantongView />;
}
