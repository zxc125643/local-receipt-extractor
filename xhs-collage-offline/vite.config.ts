import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 8765,
    proxy: {
      '/api/render': process.env.VITE_RENDER_TARGET || 'http://127.0.0.1:8767',
      '/api': 'http://127.0.0.1:8766',
      '/assets': 'http://127.0.0.1:8766',
    },
  },
})
