import { CONFIG } from 'src/global-config';

import { BudgetView } from 'src/sections/budget';

// ----------------------------------------------------------------------

export const metadata = { title: `Budget - ${CONFIG.appName}` };

export default function Page() {
  return <BudgetView />;
}
