import { CONFIG } from 'src/global-config';

import { SummaryView } from 'src/sections/summary/view';

// ----------------------------------------------------------------------

export const metadata = { title: `Ringkasan - ${CONFIG.appName}` };

export default function Page() {
  return <SummaryView />;
}
