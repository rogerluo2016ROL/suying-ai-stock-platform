import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/// <reference types="vitest/config" />
// P2 测试加固（FE-P1 review S-2 同批）：tests/sit/auth-flow.test.tsx 在单 worker
// 内连续渲染 8 个 AntD Form（LoginPage/RegisterPage 全树）+ userEvent 队列累积，
// 默认 Node heap (~1.5GB) 下会 FATAL OOM（"Ineffective mark-compacts near heap
// limit"）。forks 池每个测试文件独立进程 + 单进程隔离，避免重型 SIT 文件互相挤压。
// 仍需配合 npm test 的 NODE_OPTIONS --max-old-space-size=4096 给 worker 充足堆。
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    pool: 'forks',
    poolOptions: {
      forks: {
        singleFork: false,
        isolate: true,
      },
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api/v1/screener':    { target: 'http://localhost:8001', changeOrigin: true, timeout: 600000 },
      '/api/v1/dashboard':   { target: 'http://localhost:8004', changeOrigin: true },
      '/api/v1/prediction':  { target: 'http://localhost:8002', changeOrigin: true },
      '/api/v1/strategy':    { target: 'http://localhost:8003', changeOrigin: true },
      '/api/v1/signal':      { target: 'http://localhost:8004', changeOrigin: true },
      '/api/v1/alert':       { target: 'http://localhost:8005', changeOrigin: true },
      '/api/v1/trade':       { target: 'http://localhost:8006', changeOrigin: true },
      '/api/v1/backtest':    { target: 'http://localhost:8007', changeOrigin: true },
      '/api/v1/training':    { target: 'http://localhost:8008', changeOrigin: true },
      '/api/v1/diagnosis':   { target: 'http://localhost:8009', changeOrigin: true },
      '/api/v1/health':      { target: 'http://localhost:8080', changeOrigin: true },
      '/api/v1/data':        { target: 'http://localhost:8004', changeOrigin: true },
      '/api/v1/auth':        { target: 'http://localhost:9001', changeOrigin: true },
      '/api/v1/admin':       { target: 'http://localhost:9001', changeOrigin: true },
    },
  },
  build: {
    rollupOptions: {
      output: {
        // P1-03: split heavy vendor bundles so the initial chunk shrinks.
        // echarts (~1MB) is only used on 4 pages → its own lazy chunk.
        // antd + its icons share a chunk (splitting them triggers a circular
        // chunk warning because antd core and @ant-design/icons are mutually
        // imported). react gets its own chunk for long-term caching.
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('echarts')) return 'echarts'
            if (id.includes('antd') || id.includes('@ant-design/icons') || id.includes('/rc-') || id.includes('@rc-component') || id.includes('rc-util')) return 'antd'
            if (id.includes('/react/') || id.includes('/react-dom/') || id.includes('/react-router') || id.includes('/scheduler/')) return 'react'
          }
          return undefined
        },
      },
    },
  },
})
