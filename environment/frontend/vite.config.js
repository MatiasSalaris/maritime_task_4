import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000'
const backendWs  = backendUrl.replace(/^http/, 'ws')

export default defineConfig({
  plugins: [svelte()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': { target: backendUrl, changeOrigin: true },
      '/ws':  { target: backendWs,  ws: true, changeOrigin: true },
    },
  },
})
