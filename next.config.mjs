/**
 * Static Exports in Next.js
 *
 * 1. Set `isStaticExport = true` in `next.config.{mjs|ts}`.
 * 2. This allows `generateStaticParams()` to pre-render dynamic routes at build time.
 *
 * For more details, see:
 * https://nextjs.org/docs/app/building-your-application/deploying/static-exports
 *
 * NOTE: Remove all "generateStaticParams()" functions if not using static exports.
 */
const isStaticExport = false;

// ----------------------------------------------------------------------

/**
 * Where the FastAPI backend lives. The browser never sees this: requests
 * go to /api/* on this origin and are proxied below.
 */
const BACKEND_URL = process.env.BACKEND_URL ?? 'http://127.0.0.1:8000';

const nextConfig = {
  /**
   * Only for static export, where it matters for hosting.
   *
   * With it on for a served app, Next 308-redirects `/api/health` to
   * `/api/health/` before the rewrite runs, and the trailing slash then
   * does not match the backend's routes — so every API call becomes a
   * redirect chain.
   */
  trailingSlash: isStaticExport,
  output: isStaticExport ? 'export' : undefined,
  env: {
    BUILD_STATIC_EXPORT: JSON.stringify(isStaticExport),
  },
  /**
   * Proxy the API through this origin.
   *
   * Not a convenience — it is what makes the session cookie work. The
   * backend sets an httpOnly `SameSite=Lax` cookie, which a browser will
   * not send on a cross-origin request. Calling the backend directly
   * would mean either `SameSite=None; Secure` (so HTTPS even in
   * development, and the cookie riding along on cross-site requests) or
   * moving the token into JavaScript, where an XSS bug could read it.
   *
   * Proxying keeps everything same-origin: Lax works, no CORS is needed,
   * and the PWA only ever talks to one host — which is also what the PRD
   * specifies.
   *
   * Note `/api` is stripped: the backend's own routes are `/auth/...`,
   * `/accounts`, `/chat/...`. The prefix exists so the service worker can
   * recognise API traffic and never cache it.
   */
  async rewrites() {
    if (isStaticExport) {
      return [];
    }

    return [{ source: '/api/:path*', destination: `${BACKEND_URL}/:path*` }];
  },
  // Without --turbopack (next dev)
  webpack(config) {
    config.module.rules.push({
      test: /\.svg$/,
      use: ['@svgr/webpack'],
    });

    return config;
  },
  // With --turbopack (next dev --turbopack)
  turbopack: {
    rules: {
      '*.svg': {
        loaders: ['@svgr/webpack'],
        as: '*.js',
      },
    },
  },
};

export default nextConfig;
