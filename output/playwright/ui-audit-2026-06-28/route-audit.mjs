import { chromium } from 'playwright'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const baseUrl = process.env.UI_AUDIT_BASE_URL || 'http://127.0.0.1:3002'
const outDir = fileURLToPath(new URL('.', import.meta.url))
const screenshotDir = join(outDir, 'screenshots')
mkdirSync(screenshotDir, { recursive: true })

const routes = [
  '/',
  '/dashboard/auction',
  '/dashboard/signals',
  '/dashboard/watchlist',
  '/open-decision',
  '/open-decision/auction',
  '/open-decision/signals',
  '/open-decision/candidates',
  '/open-decision/execution',
  '/screener',
  '/screener/models',
  '/screener/factors',
  '/supply-chain-bom',
  '/supply-chain-bom/policy',
  '/supply-chain-bom/company',
  '/predictions',
  '/predictions/single',
  '/predictions/compare',
  '/predictions/backtest',
  '/signals',
  '/signals/overview',
  '/signals/history',
  '/signals/risk',
  '/trade',
  '/trade/order',
  '/trade/positions',
  '/trade/orders',
  '/trade/account',
  '/trade/brokers',
  '/strategy',
  '/strategy/detail',
  '/strategy/compare',
  '/strategy/reports',
  '/auto-trade',
  '/auto-trade/config',
  '/auto-trade/monitor',
  '/auto-trade/logs',
  '/risk',
  '/risk/overview',
  '/risk/positions',
  '/risk/strategies',
  '/risk/market',
  '/risk/audit',
  '/backtest',
  '/backtest/run',
  '/backtest/compare',
  '/backtest/trades',
  '/diagnosis',
  '/diagnosis/overview',
  '/diagnosis/model',
  '/diagnosis/compare',
  '/diagnosis/risk',
  '/training',
  '/training/tasks',
  '/training/mlflow',
  '/model-registry',
  '/data-update',
  '/data-update/overview',
  '/data-update/tables',
  '/data-update/schedule',
  '/runtime-status',
]

const forbiddenVisibleCopy = [
  '等待真实接口',
  '等待真实模型',
  '等待真实因子',
  '当前保留页面结构',
  '后续接入',
  '回退样例',
  '暂不可用',
  '暂不可达',
  '数据状态 fallback',
]

function json(data) {
  return {
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(data),
  }
}

function mockApi(pathname) {
  if (pathname.endsWith('/auth/refresh')) return { access_token: 'audit-token' }
  if (pathname.endsWith('/auth/me')) {
    return {
      id: 1,
      name: '罗杰',
      email: 'admin@suying.ai',
      role: 'admin',
      tenant_id: 'tenant-demo',
      tenant_name: '速赢AI',
      default_trade_account_id: 'paper-main',
      trade_mode: 'paper',
      broker_adapter: 'mock_qmt',
    }
  }
  if (pathname.endsWith('/alert/unread-count')) return { unread: 3 }
  if (pathname.includes('/signal/dashboard-summary')) {
    return {
      market_sentiment: { score: 72, label: '偏牛', up_stocks: 1852, down_stocks: 1432, total_stocks: 3852 },
      limit_stocks: { up_count: 87, down_count: 14 },
      signal_stocks: [{ code: '300750', name: '宁德时代', signal: '买入', change_pct: 8.2 }],
      alert_signals: [{ code: '688981', name: '中芯国际', level: 'urgent', change_pct: 5.8, reason: '半导体共振' }],
      watchlist: [{ code: '300750', name: '宁德时代', industry: '新能源', market_cap: 894200000000 }],
    }
  }
  if (pathname.endsWith('/dashboard/summary')) return { dual_consensus: [{ code: '300750', name: '宁德时代', industry: '新能源', gap_pct: 8.2, score: 90 }] }
  if (pathname.endsWith('/dashboard/auction')) return { picks: [{ code: '688981', name: '中芯国际', industry: '半导体', chg_pct: 5.8, score: 88 }] }
  if (pathname.endsWith('/screener/modes')) return { modes: [{ id: 'bi_trend_launch', name: '趋势启动 V13', cycle: '日频', style: '趋势跟踪' }] }
  if (pathname.includes('/screener/run')) return { picks: [{ code: '300750', name: '宁德时代', industry: '电力设备', price: 218.5, score: 92.5, grade: 'S' }] }
  if (pathname.includes('/screener/supply-chain/workbench')) {
    return {
      themes: [{ theme_id: 'semi', name: '半导体设备', policy_weight: 0.92, node_count: 3 }],
      nodes: [
        { node_id: 'semi-root', theme_id: 'semi', chain_id: 'semi', name: '半导体设备', level: 'L0', node_type: 'root', child_node_ids: ['etch'] },
        { node_id: 'etch', theme_id: 'semi', chain_id: 'semi', name: '刻蚀设备', level: 'L1', node_type: 'equipment', child_node_ids: [] },
      ],
      edges: [{ from_node_id: 'semi-root', to_node_id: 'etch', relation: 'contains' }],
      candidates: [{ code: '688012', name: '中微公司', industry: '半导体设备', score: 91, last_price: 180, last_change_pct: 3.5 }],
      data_freshness: { market: { latest_trade_date: '2026-06-28' } },
      model: { name: '产业链解构选股模型 V4', philosophy: '政策主题定方向，BOM拆解定环节。' },
    }
  }
  if (pathname.includes('/screener/supply-chain/mapping-review/quality')) return { total: 3, reviewable: 2, verified: 1, weak_evidence: 0 }
  if (pathname.includes('/screener/supply-chain/mapping-review/queue')) return { items: [], total: 0 }
  if (pathname.includes('/screener/chain/deconstruct')) {
    return {
      theme: { id: 'semi', name: '半导体设备' },
      view: 'upstream_downstream',
      tree: { node_id: 'semi-root', name: '半导体设备', layer: 0, children: [{ node_id: 'etch', name: '刻蚀设备', layer: 1, children: [] }] },
    }
  }
  if (pathname.includes('/screener/chain/candidates')) return { candidates: [], filter_summary: {}, resonance_summary: {} }
  if (pathname.startsWith('/api/v1/prediction/')) {
    return {
      code: '300750',
      name: '宁德时代',
      current_price: 218.5,
      pred_last_close: 242.3,
      pred_return_pct: 12.5,
      confidence: 78,
      pred_trajectory: [],
    }
  }
  if (pathname.includes('/signal/live')) return { signals: [{ code: '300750', name: '宁德时代', signal: '买入', strength: 82, reason: '竞价强 + 资金共振', risk: '低' }] }
  if (pathname.includes('/signal/history')) return { history: [{ code: '300750', name: '宁德时代', signal: '买入', date: '2026-06-25', hit: true, return_pct: 8.2 }] }
  if (pathname.includes('/signal/analyze')) return { code: '300750', risk_score: 28, verdict: 'pass', blockers: [] }
  if (pathname.includes('/signal/data-status')) {
    return {
      status: 'ok',
      total_tables: 4,
      active_tables: 4,
      total_rows: 982000,
      sources: [{ key: 'daily_kline', name: '日线行情', category: '行情', source: 'Tushare', update: '每日', rows: 620000, min_date: '2024-01-01', max_date: '2026-06-28', status: 'active' }],
      sync_map: { daily_kline: { mode: 'post_market', days_default: 30, desc: '日线行情' } },
    }
  }
  if (pathname.endsWith('/signal/sync-schedules')) return { schedules: [{ table_key: 'daily_kline', days_back: 30, interval_minutes: 1440, enabled: true, next_sync_at: '17:20' }] }
  if (pathname.endsWith('/trade/account')) return { total_assets: 1000000, available: 320000, market_value: 680000, total_pnl: 0.082 }
  if (pathname.endsWith('/trade/positions')) return { positions: [{ code: '300750', name: '宁德时代', volume: 100, cost: 202.1, pnl: 8.2 }] }
  if (pathname.endsWith('/trade/orders')) return { orders: [{ id: 'ORD-1', code: '300750', direction: 'BUY', volume: 100, price: 218.5, status: 'filled' }] }
  if (pathname.includes('/trade/risk-verdicts')) return { items: [], total: 0 }
  if (pathname.includes('/trade/decision-contexts')) return { items: [], total: 0 }
  if (pathname.endsWith('/strategy/list')) return { strategies: [{ id: 'strat-demo', name: '模拟趋势策略', status: 'active', trade_mode: 'paper', picks_count: 3 }] }
  if (pathname.includes('/strategy/') && pathname.endsWith('/log')) return { logs: [{ timestamp: '09:32:15', level: 'info', message: '订单预检通过', details: { decision_context_id: 'DC-1', plan_id: 'PLAN-1', code: '300750' } }] }
  if (pathname.endsWith('/strategy/templates')) return { templates: [] }
  if (pathname.endsWith('/strategy/plans')) return { plans: [] }
  if (pathname.endsWith('/backtest/factors')) return { factors: [] }
  return {}
}

let browser
try {
  browser = await chromium.launch({ channel: 'chrome', headless: true })
} catch {
  browser = await chromium.launch({ headless: true })
}

const context = await browser.newContext({ viewport: { width: 1440, height: 960 } })
const page = await context.newPage()
const consoleErrors = []
const pageErrors = []

page.on('console', msg => {
  if (msg.type() === 'error') consoleErrors.push(msg.text())
})
page.on('pageerror', error => pageErrors.push(error.message))

await page.route('**/api/v1/**', async route => {
  const url = new URL(route.request().url())
  await route.fulfill(json(mockApi(url.pathname)))
})

await page.route('**/health', route => route.fulfill(json({ status: 'online' })))

const results = []

for (const routePath of routes) {
  consoleErrors.length = 0
  pageErrors.length = 0
  const url = `${baseUrl}${routePath}`
  const result = { route: routePath, ok: true, issues: [] }
  try {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 20_000 })
    await page.waitForSelector('[data-testid="app-shell"], .prototype-page', { timeout: 10_000 })
    await page.waitForTimeout(450)
    const currentUrl = page.url()
    const text = await page.locator('body').innerText({ timeout: 5_000 })
    const headingCount = await page.locator('h1,h2,h3,.prototype-page-title').count()
    const cardCount = await page.locator('.prototype-card,.ant-card,.kpis,.tbl').count()
    if (currentUrl.includes('/login')) result.issues.push('redirected-to-login')
    if (headingCount === 0) result.issues.push('missing-heading')
    if (cardCount === 0) result.issues.push('missing-business-content')
    for (const copy of forbiddenVisibleCopy) {
      if (text.includes(copy)) result.issues.push(`forbidden-copy:${copy}`)
    }
    if (pageErrors.length) result.issues.push(`pageerror:${pageErrors.join(' | ')}`)
    if (consoleErrors.some(item => /TypeError|ReferenceError|SyntaxError|Cannot read/i.test(item))) {
      result.issues.push(`console:${consoleErrors.join(' | ')}`)
    }
  } catch (error) {
    result.issues.push(`exception:${error.message}`)
  }
  if (result.issues.length) {
    result.ok = false
    await page.screenshot({ path: join(screenshotDir, `${routePath.replace(/[^a-z0-9]+/gi, '_') || 'root'}.png`), fullPage: true })
  }
  results.push(result)
}

await browser.close()

writeFileSync(join(outDir, 'route-audit-results.json'), JSON.stringify(results, null, 2))

const failures = results.filter(item => !item.ok)
console.log(JSON.stringify({ total: results.length, failures: failures.length, failedRoutes: failures }, null, 2))
if (failures.length) process.exit(1)
