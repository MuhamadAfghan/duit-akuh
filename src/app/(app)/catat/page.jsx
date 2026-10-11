import { CONFIG } from 'src/global-config';

import { CatatView } from 'src/sections/catat';

// ----------------------------------------------------------------------

export const metadata = { title: `Catat manual - ${CONFIG.appName}` };

export default function Page() {
  return <CatatView />;
}
