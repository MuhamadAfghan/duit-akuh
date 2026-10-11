import { CONFIG } from 'src/global-config';

import { TargetView } from 'src/sections/target';

// ----------------------------------------------------------------------

export const metadata = { title: `Target - ${CONFIG.appName}` };

export default function Page() {
  return <TargetView />;
}
