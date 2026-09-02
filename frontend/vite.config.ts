import { fileURLToPath } from 'node:url'

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const srcDir = fileURLToPath(new URL('./src', import.meta.url))

// Dev server proxies /api to the FastAPI backend so the browser sees one
// origin and CORS never enters the picture during development.
//
// `resolve.alias` mirrors tsconfig.json's `paths` — tsconfig's alone only
// satisfies the type checker, not the bundler, which would otherwise fail
// to resolve every `@/...` import at build/dev time.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': srcDir },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
