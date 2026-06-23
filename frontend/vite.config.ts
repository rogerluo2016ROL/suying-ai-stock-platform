import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const authServiceTarget = process.env.VITE_AUTH_SERVICE_URL || 'http://localhost:9001'
const screenerServiceTarget = process.env.VITE_SCREENER_SERVICE_URL || 'http://localhost:8001'
const predictionServiceTarget = process.env.VITE_PREDICTION_SERVICE_URL || 'http://localhost:8002'
const strategyServiceTarget = process.env.VITE_STRATEGY_SERVICE_URL || 'http://localhost:8003'
const signalServiceTarget = process.env.VITE_SIGNAL_SERVICE_URL || 'http://localhost:8004'
const alertServiceTarget = process.env.VITE_ALERT_SERVICE_URL || 'http://localhost:8005'
const tradeServiceTarget = process.env.VITE_TRADE_SERVICE_URL || 'http://localhost:8006'
const backtestServiceTarget = process.env.VITE_BACKTEST_SERVICE_URL || 'http://localhost:8007'
const trainingServiceTarget = process.env.VITE_TRAINING_SERVICE_URL || 'http://localhost:8008'
const diagnosisServiceTarget = process.env.VITE_DIAGNOSIS_SERVICE_URL || 'http://localhost:8009'
const gatewayServiceTarget = process.env.VITE_GATEWAY_SERVICE_URL || 'http://localhost:8080'

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
      '/api/v1/screener':    { target: screenerServiceTarget, changeOrigin: true, timeout: 600000 },
      '/api/v1/dashboard':   { target: signalServiceTarget, changeOrigin: true },
      '/api/v1/prediction':  { target: predictionServiceTarget, changeOrigin: true },
      '/api/v1/strategy':    { target: strategyServiceTarget, changeOrigin: true },
      '/api/v1/signal':      { target: signalServiceTarget, changeOrigin: true },
      '/api/v1/alert':       { target: alertServiceTarget, changeOrigin: true },
      '/api/v1/trade':       { target: tradeServiceTarget, changeOrigin: true },
      '/api/v1/backtest':    { target: backtestServiceTarget, changeOrigin: true },
      '/api/v1/training':    { target: trainingServiceTarget, changeOrigin: true },
      '/api/v1/diagnosis':   { target: diagnosisServiceTarget, changeOrigin: true },
      '/api/v1/health':      { target: gatewayServiceTarget, changeOrigin: true },
      '/api/v1/data':        { target: signalServiceTarget, changeOrigin: true },
      '/api/v1/auth':        { target: authServiceTarget, changeOrigin: true },
      '/api/v1/admin':       { target: authServiceTarget, changeOrigin: true },
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
