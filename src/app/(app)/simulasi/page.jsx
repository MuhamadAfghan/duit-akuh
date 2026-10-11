import { CONFIG } from 'src/global-config';

import { SimulasiView } from 'src/sections/simulasi';

// ----------------------------------------------------------------------

export const metadata = { title: `Simulasi - ${CONFIG.appName}` };

export default function Page() {
  return <SimulasiView />;
}
