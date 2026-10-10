import { CONFIG } from 'src/global-config';

import { PlaceholderView } from 'src/sections/placeholder';

// ----------------------------------------------------------------------

export const metadata = { title: `Data - ${CONFIG.appName}` };

export default function Page() {
  return (
    <PlaceholderView
      title="Data"
      description="Daftar transaksi, kantong dan target. Setiap objek punya aksi “Bahas di chat” yang membawanya ke obrolan utama (bagian 3)."
    />
  );
}
