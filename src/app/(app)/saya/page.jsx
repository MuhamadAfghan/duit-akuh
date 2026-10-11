import { CONFIG } from 'src/global-config';

import { ProfilView } from 'src/sections/profil';

// ----------------------------------------------------------------------

export const metadata = { title: `Saya - ${CONFIG.appName}` };

export default function Page() {
  return <ProfilView />;
}
