import { CONFIG } from 'src/global-config';
import { themeConfig } from 'src/theme/theme-config';

// ----------------------------------------------------------------------

/**
 * PWA manifest (PRD FR16).
 *
 * Icons are generated from public/logo/app-icon.svg by `npm run gen:icons`.
 * `display: standalone` plus start_url/scope are what make the app
 * installable and launchable from the home screen icon (AC15).
 */
export default function manifest() {
  return {
    name: CONFIG.appName,
    short_name: CONFIG.appName,
    description: 'Catat keuangan lewat percakapan.',
    start_url: '/',
    scope: '/',
    display: 'standalone',
    orientation: 'any',
    lang: 'id-ID',
    dir: 'ltr',
    background_color: '#FFFFFF',
    theme_color: themeConfig.palette.primary.main,
    icons: [
      { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
      { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
      {
        src: '/icons/icon-maskable-192.png',
        sizes: '192x192',
        type: 'image/png',
        purpose: 'maskable',
      },
      {
        src: '/icons/icon-maskable-512.png',
        sizes: '512x512',
        type: 'image/png',
        purpose: 'maskable',
      },
    ],
  };
}
