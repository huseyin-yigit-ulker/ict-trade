import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  base: '/ict-trade/', // <-- Eğer repo adın buysa burayı güncelle. Yoksa '/' kalsın.
})