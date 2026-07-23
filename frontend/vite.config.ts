import { defineConfig } from 'vite'
import type { Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import { execFile } from 'node:child_process'
import { resolveProxyTargets } from './proxyTargets'

const proxyTargets = resolveProxyTargets(process.env)
const serviceHealthTargets: Record<string, string> = {
  auth: proxyTargets.auth,
  admin: proxyTargets.auth,
  screener: proxyTargets.screener,
  prediction: proxyTargets.prediction,
  strategy: proxyTargets.strategy,
  signal: proxyTargets.signal,
  dashboard: proxyTargets.screener,
  data: proxyTargets.signal,
  alert: proxyTargets.alert,
  trade: proxyTargets.trade,
  backtest: proxyTargets.backtest,
  training: proxyTargets.training,
  diagnosis: proxyTargets.diagnosis,
}
const serviceHealthProxy = Object.fromEntries(
  Object.entries(serviceHealthTargets).map(([service, target]) => [
    `/api/v1/${service}/health`,
    {
      target,
      changeOrigin: true,
      rewrite: () => (service === 'auth' || service === 'admin' ? '/api/health' : '/api/v1/health'),
    },
  ]),
)

function queryIndexCloseSnapshot(): Promise<Record<string, unknown>> {
  const sql = `
    WITH latest AS (
      SELECT MAX(trade_date) AS trade_date
      FROM index_daily
      WHERE code IN ('000001','399001','399006','899050')
    )
    SELECT code, close, change_pct, trade_date
    FROM index_daily
    WHERE trade_date = (SELECT trade_date FROM latest)
      AND code IN ('000001','399001','399006','899050')
    ORDER BY code
  `
  return new Promise((resolve) => {
    execFile(
      'psql',
      ['-h', '127.0.0.1', '-p', '6432', '-U', 'kronos', '-d', 'kronos', '-At', '-F', '\t', '-c', sql],
      // dev-only 中间件：PGPASSWORD 走环境变量或 ~/.pgpass，不在仓库硬编码密码；
      // 失败时走下方 fallback_reason 优雅降级
      { env: { ...process.env }, timeout: 5000 },
      (error, stdout) => {
        if (error) {
          resolve({ source: 'index_daily_close', as_of: null, data: { diff: [] }, fallback_reason: String(error.message || error) })
          return
        }
        const labels: Record<string, string> = {
          '000001': '上证',
          '399001': '深成',
          '399006': '创业板',
          '899050': '北证50',
        }
        const diff = stdout
          .trim()
          .split('\n')
          .filter(Boolean)
          .map((line) => {
            const [code, close, changePct, tradeDate] = line.split('\t')
            return { f12: code, f14: labels[code] || code, f2: Number(close), f3: Number(changePct), f4: null, f6: null, trade_date: tradeDate }
          })
        resolve({
          source: 'index_daily_close',
          as_of: diff[0]?.trade_date || null,
          data: { diff },
        })
      },
    )
  })
}

function localIndexClosePlugin(): Plugin {
  return {
    name: 'local-index-close-snapshot',
    configureServer(server) {
      server.middlewares.use('/api/v1/screener/market/index-quotes', async (_req, res) => {
        const payload = await queryIndexCloseSnapshot()
        res.setHeader('Content-Type', 'application/json; charset=utf-8')
        res.end(JSON.stringify(payload))
      })
    },
  }
}

/// <reference types="vitest/config" />
// P2 测试加固（FE-P1 review S-2 同批）：tests/sit/auth-flow.test.tsx 在单 worker
// 内连续渲染 8 个 AntD Form（LoginPage/RegisterPage 全树）+ userEvent 队列累积，
// 默认 Node heap (~1.5GB) 下会 FATAL OOM（"Ineffective mark-compacts near heap
// limit"）。forks 池每个测试文件独立进程 + 单进程隔离，避免重型 SIT 文件互相挤压。
// 仍需配合 npm test 的 NODE_OPTIONS --max-old-space-size=4096 给 worker 充足堆。
export default defineConfig({
  plugins: [localIndexClosePlugin(), react()],
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
      ...serviceHealthProxy,
      '/api/v1/screener':    { target: proxyTargets.screener, changeOrigin: true, timeout: 600000 },
      '/api/v1/dashboard':   { target: proxyTargets.screener, changeOrigin: true },
      '/api/v1/prediction':  { target: proxyTargets.prediction, changeOrigin: true },
      '/api/v1/strategy':    { target: proxyTargets.strategy, changeOrigin: true },
      '/api/v1/signal':      { target: proxyTargets.signal, changeOrigin: true },
      '/api/v1/alert':       { target: proxyTargets.alert, changeOrigin: true },
      '/api/v1/trade':       { target: proxyTargets.trade, changeOrigin: true },
      '/api/v1/backtest':    { target: proxyTargets.backtest, changeOrigin: true },
      '/api/v1/training':    { target: proxyTargets.training, changeOrigin: true },
      '/api/v1/diagnosis':   { target: proxyTargets.diagnosis, changeOrigin: true },
      '/health':             { target: proxyTargets.gateway, changeOrigin: true },
      '/api/v1/health':      { target: proxyTargets.gateway, changeOrigin: true, rewrite: () => '/health' },
      '/api/v1/data':        { target: proxyTargets.signal, changeOrigin: true },
      '/api/v1/auth':        { target: proxyTargets.auth, changeOrigin: true },
      '/api/v1/admin':       { target: proxyTargets.auth, changeOrigin: true },
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
