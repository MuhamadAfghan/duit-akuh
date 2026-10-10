import { CONFIG } from 'src/global-config';

import { DataView } from 'src/sections/data/view';

// ----------------------------------------------------------------------

export const metadata = { title: `Data - ${CONFIG.appName}` };

export default function Page() {
  return <DataView />;
}
