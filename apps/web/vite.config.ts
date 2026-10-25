import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Phase 05: the axios client (src/lib/http.ts) is SAME-ORIGIN by default —
// baseURL falls back to '', so requests like /api/... and /health go to this
// dev server and are proxied here to FastAPI on :8000 (no CORS, no .env needed
// locally). Set VITE_API_URL to a full origin to bypass the proxy (deployed).
// Tailwind v4: plugin goes AFTER react(); design tokens live in src/index.css (@theme).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          cytoscape: ['cytoscape'],
          react: ['react', 'react-dom', 'react-router-dom'],
        },
      },
    },
  },
  server: {
    port: 5173,
    // sandboxed live previews reach the dev server under foreign hostnames
    allowedHosts: true,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/health': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
