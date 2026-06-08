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

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react(), spaFallback404()],
  envPrefix: ['VITE_', 'BACKTESTING_'],
  base: '/',
})
