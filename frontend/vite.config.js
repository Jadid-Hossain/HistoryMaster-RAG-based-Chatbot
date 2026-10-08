import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev server proxies /api to FastAPI; production build is served by FastAPI itself.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
  },
})
