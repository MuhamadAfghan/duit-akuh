import { CONFIG } from 'src/global-config';

import { PlaceholderView } from 'src/sections/placeholder';

// ----------------------------------------------------------------------

export const metadata = { title: `Ringkasan - ${CONFIG.appName}` };

export default function Page() {
  return (
    <PlaceholderView
      title="Ringkasan"
      description="Saldo per kantong, uang bebas pakai, pengeluaran dan progres target akan tampil di sini — dihitung backend dari data yang sama dengan chat (FR09)."
    />
  );
}
