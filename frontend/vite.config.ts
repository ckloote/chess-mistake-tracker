import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Backend runs on :8000 in dev. Proxying /api keeps frontend fetch URLs
// origin-relative so the same code paths work in production where FastAPI
// will serve the built bundle.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: false,
      },
    },
  },
})
