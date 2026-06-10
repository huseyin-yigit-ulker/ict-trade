import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { copyFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'

const here = fileURLToPath(new URL('.', import.meta.url))

// Static-host SPA fallback (Render): Render serves 404.html for any path that
// doesn't match a file. Emitting a 404.html copy of index.html makes deep links
// like /main/live boot the app — React Router then renders the route (unknown
// routes fall through to the App-level `* -> /main/live` redirect). Render does
// NOT honour Netlify-style _redirects here, so this is the reliable fallback.
function spaFallback404() {
  return {
    name: 'spa-fallback-404',
    closeBundle() {
      try {
        copyFileSync(resolve(here, 'dist/index.html'), resolve(here, 'dist/404.html'))
      } catch { /* dist absent on non-build commands */ }
    },
  }
}

// Content-Security-Policy, injected at BUILD ONLY (dev needs Vite/React-refresh
// inline scripts which a strict policy would block). A static host can't set
// response headers, so a <meta> tag is the strongest available delivery.
// 'unsafe-inline' in style-src is required by React inline style attributes.
// frame-ancestors can't be expressed via <meta>; set it at the host if possible.
const CSP = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
  "font-src https://fonts.gstatic.com",
  "img-src 'self' data:",
  "connect-src 'self' https://*.supabase.co https://fapi.binance.com https://api.binance.com",
  "frame-src https://s.tradingview.com",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join('; ')

function cspInject() {
  return {
    name: 'csp-inject',
    apply: 'build',
    transformIndexHtml(html) {
      return html.replace(
        '<meta charset="UTF-8" />',
        `<meta charset="UTF-8" />\n    <meta http-equiv="Content-Security-Policy" content="${CSP}" />`,
      )
    },
  }
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react(), cspInject(), spaFallback404()],
  // SECURITY: never use the broad 'BACKTESTING_' prefix here — .env also holds
  // BACKTESTING_DB_CONNECTION_STRING (Postgres password) and a wide prefix
  // would expose it to the browser. Only the public Supabase REST vars and the
  // table name are allowed through.
  envPrefix: ['VITE_', 'BACKTESTING_VITE_', 'BACKTESTING_DB_TABLE'],
  base: '/',
})
