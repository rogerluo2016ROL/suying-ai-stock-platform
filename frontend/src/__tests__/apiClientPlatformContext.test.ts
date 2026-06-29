import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import api, {
  alertApi,
  backtestApi,
  chainApi,
  clearPlatformContext,
  diagnosisApi,
  healthApi,
  injectPlatformContext,
  predictionApi,
  screenerApi,
  signalApi,
  strategyApi,
  tradeApi,
  workbenchApi,
} from '../api/client'
import type { PlatformSession } from '../types/platform'

const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  server.resetHandlers()
  clearPlatformContext()
})
afterAll(() => server.close())

const session: PlatformSession = {
  tenantId: 'tenant-alpha',
  tenantName: 'Alpha 机构',
  ownerUserId: '12',
  accountId: 'paper-001',
  visibility: 'private',
  dataScope: 'account',
  roleView: 'trader',
  userName: '毕师傅',
  tradeMode: 'paper',
  brokerAdapter: 'paper',
  cloudReady: true,
}

describe('api platform context headers', () => {
  it('queries gateway health at root /health instead of /api/v1/health', async () => {
    let calledPath = ''

    server.use(
      http.get('/health', ({ request }) => {
        calledPath = new URL(request.url).pathname
        return HttpResponse.json({ status: 'healthy' })
      }),
    )

    await healthApi.gateway()

    expect(calledPath).toBe('/health')
  })

  it('treats service /health status=healthy as online', async () => {
    server.use(
      http.get('/api/v1/trade/health', () => HttpResponse.json({ status: 'healthy' })),
    )

    await expect(healthApi.checkOnline('trade')).resolves.toBe(true)
  })

  it('attaches tenant and account boundaries to API requests', async () => {
    let tenantId: string | null = null
    let accountId: string | null = null
    let dataScope: string | null = null

    server.use(
      http.get('/api/v1/platform-context-test', ({ request }) => {
        tenantId = request.headers.get('X-Tenant-Id')
        accountId = request.headers.get('X-Trade-Account-Id')
        dataScope = request.headers.get('X-Data-Scope')
        return HttpResponse.json({ ok: true })
      }),
    )

    injectPlatformContext(() => session)
    await api.get('/platform-context-test')

    expect(tenantId).toBe('tenant-alpha')
    expect(accountId).toBe('paper-001')
    expect(dataScope).toBe('account')
  })

  it('uses the API gateway /api/v1 prefix for all frontend service clients', async () => {
    const paths: string[] = []

    server.use(
      http.all('/api/v1/*', ({ request }) => {
        paths.push(new URL(request.url).pathname)
        return HttpResponse.json({})
      }),
    )

    await Promise.all([
      screenerApi.getModes(),
      predictionApi.getStatus(),
      strategyApi.getTemplates(),
      signalApi.getLevels(),
      signalApi.getScreeningDashboardSummary(),
      signalApi.getDashboardAuction(),
      signalApi.getDataStatus(),
      signalApi.triggerSync('daily_kline', 30),
      signalApi.getSyncSchedules(),
      alertApi.getUnreadCount(),
      tradeApi.getOrders(),
      backtestApi.getFactors(),
      diagnosisApi.getHistory(),
      chainApi.getCandidates(),
    ])

    expect(paths).toEqual(expect.arrayContaining([
      '/api/v1/screener/modes',
      '/api/v1/prediction/status',
      '/api/v1/strategy/templates',
      '/api/v1/signal/levels',
      '/api/v1/dashboard/summary',
      '/api/v1/dashboard/auction',
      '/api/v1/signal/data-status',
      '/api/v1/signal/trigger-sync',
      '/api/v1/signal/sync-schedules',
      '/api/v1/alert/unread-count',
      '/api/v1/trade/orders',
      '/api/v1/backtest/factors',
      '/api/v1/diagnosis/history',
      '/api/v1/screener/chain/candidates',
    ]))
  })

  it('queries risk verdicts with platform scope headers and filters', async () => {
    let tenantId: string | null = null
    let accountId: string | null = null
    let query = ''

    server.use(
      http.get('/api/v1/trade/risk-verdicts', ({ request }) => {
        const url = new URL(request.url)
        tenantId = request.headers.get('X-Tenant-Id')
        accountId = request.headers.get('X-Trade-Account-Id')
        query = url.search
        return HttpResponse.json({ total: 0, page: 1, page_size: 20, records: [] })
      }),
    )

    injectPlatformContext(() => session)
    await tradeApi.getRiskVerdicts({
      result: 'reject',
      trade_mode: 'paper',
      code: '300750',
      decision_context_id: 'CTX-1',
      order_id: 'ORD-1',
      plan_id: 'PLAN-1',
      candidate_id: 'CAND-1',
      page: 1,
      page_size: 20,
    })

    expect(tenantId).toBe('tenant-alpha')
    expect(accountId).toBe('paper-001')
    expect(query).toContain('result=reject')
    expect(query).toContain('trade_mode=paper')
    expect(query).toContain('code=300750')
    expect(query).toContain('decision_context_id=CTX-1')
    expect(query).toContain('order_id=ORD-1')
    expect(query).toContain('plan_id=PLAN-1')
    expect(query).toContain('candidate_id=CAND-1')
    expect(query).toContain('page_size=20')
  })

  it('queries decision contexts with platform scope headers and lineage filters', async () => {
    let tenantId: string | null = null
    let accountId: string | null = null
    let query = ''

    server.use(
      http.get('/api/v1/trade/decision-contexts', ({ request }) => {
        const url = new URL(request.url)
        tenantId = request.headers.get('X-Tenant-Id')
        accountId = request.headers.get('X-Trade-Account-Id')
        query = url.search
        return HttpResponse.json({ total: 0, page: 1, page_size: 20, records: [] })
      }),
    )

    injectPlatformContext(() => session)
    await tradeApi.getDecisionContexts({
      decision_context_id: 'CTX-1',
      code: '300750',
      plan_id: 'PLAN-1',
      candidate_id: 'CAND-1',
      page: 1,
      page_size: 20,
    })

    expect(tenantId).toBe('tenant-alpha')
    expect(accountId).toBe('paper-001')
    expect(query).toContain('decision_context_id=CTX-1')
    expect(query).toContain('code=300750')
    expect(query).toContain('plan_id=PLAN-1')
    expect(query).toContain('candidate_id=CAND-1')
  })

  it('queries workbench view models through the gateway envelope', async () => {
    let tenantId: string | null = null
    let accountId: string | null = null
    let dataScope: string | null = null
    let calledPath = ''

    server.use(
      http.get('/api/v1/workbench/p0', ({ request }) => {
        const url = new URL(request.url)
        calledPath = url.pathname
        tenantId = request.headers.get('X-Tenant-Id')
        accountId = request.headers.get('X-Trade-Account-Id')
        dataScope = request.headers.get('X-Data-Scope')
        return HttpResponse.json({
          status: 'ok',
          page: { module: 'p0', route: '/workflow/p0', title: 'P0 主链路' },
          context: { tenant_id: 'tenant-alpha', account_id: 'paper-001', data_scope: 'account' },
          data_domain: 'account',
          freshness: { status: 'fresh', as_of: '2026-06-28T09:30:00+08:00' },
          lineage: { candidate_id: 'CAND-1', plan_id: 'PLAN-1' },
          sections: [{ key: 'main_flow', title: '主链路', state: 'ready', items: [] }],
          actions: [{ key: 'open_candidate', label: '进入候选池', enabled: true }],
        })
      }),
    )

    injectPlatformContext(() => session)
    const response = await workbenchApi.getPage('p0')

    expect(calledPath).toBe('/api/v1/workbench/p0')
    expect(tenantId).toBe('tenant-alpha')
    expect(accountId).toBe('paper-001')
    expect(dataScope).toBe('account')
    expect(response.data.page.module).toBe('p0')
    expect(response.data.sections[0].key).toBe('main_flow')
  })
})
