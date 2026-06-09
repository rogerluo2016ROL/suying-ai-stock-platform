import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api/v1/screener':    { target: 'http://localhost:8001', changeOrigin: true },
      '/api/v1/prediction':  { target: 'http://localhost:8002', changeOrigin: true },
      '/api/v1/strategy':    { target: 'http://localhost:8003', changeOrigin: true },
      '/api/v1/signal':      { target: 'http://localhost:8004', changeOrigin: true },
      '/api/v1/alert':       { target: 'http://localhost:8005', changeOrigin: true },
      '/api/v1/trade':       { target: 'http://localhost:8006', changeOrigin: true },
      '/api/v1/backtest':    { target: 'http://localhost:8007', changeOrigin: true },
      '/api/v1/diagnosis':   { target: 'http://localhost:8009', changeOrigin: true },
      '/api/v1/health':      { target: 'http://localhost:8001', changeOrigin: true },
    },
  },
})
