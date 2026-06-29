import fs from 'node:fs/promises'
import path from 'node:path'
import { chromium } from 'playwright'

const baseUrl = process.env.UAT_BASE_URL || 'http://127.0.0.1:3000'
const outDir = path.resolve('output/playwright/full-platform-uat-2026-06-28')

const routes = [
  '/', '/dashboard/auction', '/dashboard/signals', '/dashboard/watchlist',
  '/open-decision', '/open-decision/auction', '/open-decision/signals', '/open-decision/candidates', '/open-decision/execution',
  '/screener', '/screener/models', '/screener/factors',
  '/supply-chain-bom', '/supply-chain-bom/policy', '/supply-chain-bom/company',
  '/predictions', '/predictions/single', '/predictions/compare', '/predictions/backtest',
  '/signals', '/signals/overview', '/signals/history', '/signals/risk',
  '/trade', '/trade/order', '/trade/positions', '/trade/orders', '/trade/account', '/trade/brokers',
  '/trade/audit-log', '/trade/risk-verdicts', '/trade/decision-contexts',
  '/auto-trade', '/auto-trade/config', '/auto-trade/monitor', '/auto-trade/logs',
  '/strategy', '/strategy/detail', '/strategy/compare', '/strategy/reports',
  '/risk', '/risk/overview', '/risk/positions', '/risk/strategies', '/risk/market', '/risk/audit',
  '/backtest', '/backtest/run', '/backtest/compare', '/backtest/trades',
  '/diagnosis', '/diagnosis/overview', '/diagnosis/model', '/diagnosis/compare', '/diagnosis/risk',
  '/training', '/training/tasks', '/training/mlflow',
  '/model-registry',
  '/data-update', '/data-update/overview', '/data-update/tables', '/data-update/schedule',
  '/runtime', '/runtime-status', '/workflow/p0', '/platform/upgrade',
]

function jsonResponse(payload, status = 200) {
  return {
    status,
    contentType: 'application/json',
    body: JSON.stringify(payload),
  }
}

function apiFallback(url) {
  if (url.includes('/auth/refresh')) return { access_token: 'uat-token', expires_in: 900 }
  if (url.includes('/auth/me')) {
    return {
      id: 1,
      name: '罗杰',
      email: 'admin@suying.ai',
      role: 'admin',
      tenant_id: 'platform',
      tenant_name: '平台运营',
      default_trade_account_id: 'paper-admin',
      trade_mode: 'paper',
      broker_adapter: 'paper',
    }
  }
  if (url.includes('/alert/unread-count')) return { unread: 3 }
  if (url.includes('/trade/broker/status')) {
    return {
      connected: false,
      status: 'disconnected',
      broker_name: 'paper',
      account_id: 'paper-admin',
      adapter: 'paper',
      trade_mode: 'paper',
    }
  }
  if (url.includes('/trade/account')) return { trade_mode: 'paper', total_capital: 1000000, available: 900000, market_value: 100000 }
  if (url.includes('/trade/positions')) return { trade_mode: 'paper', positions: [] }
  if (url.includes('/trade/orders')) return { orders: [], total: 0, page: 1, page_size: 50 }
  if (url.includes('/trade/risk-verdicts')) return { records: [], total: 0, page: 1, page_size: 50 }
  if (url.includes('/trade/decision-contexts')) return { records: [], total: 0, page: 1, page_size: 50 }
  if (url.includes('/trade/audit-logs')) return { logs: [], total: 0, page: 1, page_size: 50 }
  if (url.includes('/trade/risk-config')) return { large_order_threshold: 500000, max_single_amount: 500000 }
  if (url.includes('/trade/circuit-breaker')) return { breakers: [] }
  if (url.includes('/workbench/')) {
    return {
      page: 'uat',
      context: { tenant_id: 'platform', account_id: 'paper-admin' },
      data_domain: 'mocked-browser-uat',
      freshness: { status: 'fresh' },
      lineage: [],
      sections: [],
      actions: [],
    }
  }
  return {}
}

await fs.mkdir(outDir, { recursive: true })
const browser = await chromium.launch({ channel: process.env.PW_CHANNEL || 'chrome', headless: true })
const context = await browser.newContext({
  viewport: { width: 1440, height: 960 },
  deviceScaleFactor: 1,
})

await context.route('**/api/v1/**', async route => {
  const request = route.request()
  const url = request.url()
  if (request.method() === 'OPTIONS') {
    await route.fulfill(jsonResponse({ ok: true }))
    return
  }
  await route.fulfill(jsonResponse(apiFallback(url)))
})

const page = await context.newPage()
const records = []

for (const route of routes) {
  const routeErrors = []
  const onPageError = error => routeErrors.push(error.message)
  page.once('pageerror', onPageError)
  const url = `${baseUrl}${route}`
  const response = await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 })
  await page.waitForSelector('[data-testid="app-shell"]', { timeout: 15000 })
  await page.waitForTimeout(250)
  const text = await page.locator('main.content').innerText({ timeout: 10000 }).catch(() => '')
  const screenshotName = `${String(records.length + 1).padStart(2, '0')}-${route === '/' ? 'root' : route.slice(1).replaceAll('/', '-')}.png`
  await page.screenshot({ path: path.join(outDir, screenshotName), fullPage: true })
  records.push({
    route,
    status: response?.status() || 0,
    shell: await page.locator('[data-testid="app-shell"]').count(),
    textLength: text.trim().length,
    screenshot: screenshotName,
    pageErrors: routeErrors,
  })
  page.removeListener('pageerror', onPageError)
}

await fs.writeFile(
  path.join(outDir, 'route-smoke-results.json'),
  JSON.stringify({
    baseUrl,
    routeCount: routes.length,
    generatedAt: new Date().toISOString(),
    failures: records.filter(item => item.status >= 400 || item.shell < 1 || item.textLength < 20 || item.pageErrors.length > 0),
    records,
  }, null, 2),
)

await browser.close()
