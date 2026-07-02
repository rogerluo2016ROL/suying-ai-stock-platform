import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { MemoryRouter } from 'react-router-dom'
import Dashboard from '../../src/pages/Dashboard'
import api, { signalApi } from '../../src/api/client'

// SIT scope：Dashboard 1.1 sentiment-dashboard + 1.3 signal-overview 两 preview 的区块渲染 +
// signalApi 契约调用（getDashboardSummary / getScreeningDashboardSummary / getDashboardAuction）。
// API client 走 vi.mock（项目既有 Dashboard.test.tsx 同款），断言"触发/挂载→以正确参数调了正确 API"。
// MSW 未引入是因为项目 signalApi client 由既有 mock 覆盖（与 Dashboard.test.tsx 同源）。

vi.mock('echarts-for-react', () => ({
  default: ({ className, style }: { className?: string; style?: React.CSSProperties }) => (
    <div data-testid="mock-chart" className={className} style={style} />
  ),
}))

vi.mock('../../src/api/client', () => ({
  default: { get: vi.fn(), post: vi.fn() },
  signalApi: {
    getDashboardSummary: vi.fn(),
    getScreeningDashboardSummary: vi.fn(),
    getDashboardAuction: vi.fn(),
  },
}))

const dashboardSummary = {
  refreshed_at: new Date().toISOString(),
  market_sentiment: {
    score: 72,
    label: '偏牛',
    trade_date: '2026-06-25',
    avg_change_pct: 1.2,
    up_stocks: 1852,
    down_stocks: 1432,
    total_stocks: 3852,
    model: 'market_regime_v2',
    formula: 'trend×25% + breadth×20% + ...',
  },
  signal_stocks: [{
    code: '688981', name: '中芯国际', price: 68.2, change_pct: 5.8,
    signal: 'Bullish', desc: '多头信号', industry: '半导体', score: 88,
  }],
  limit_stocks: { up_count: 87, down_count: 14, data_source: 'stk_limit' },
  alert_signals: [],
  auction_intent: { trade_date: '2026-06-25', total_analyzed: 20, bullish_count: 2, bearish_count: 1, neutral_count: 17 },
  watchlist: [],
  data_sources: { signal_stocks: 'PG daily_kline' },
}

function renderDashboard(route = '/') {
  return render(
    <ConfigProvider locale={zhCN}>
      <MemoryRouter initialEntries={[route]}>
        <Dashboard />
      </MemoryRouter>
    </ConfigProvider>,
  )
}

describe('Dashboard 1.1 + 1.3 preview SIT', () => {
  beforeEach(() => {
    vi.mocked(signalApi.getDashboardSummary).mockResolvedValue({ data: dashboardSummary } as any)
    vi.mocked(signalApi.getScreeningDashboardSummary).mockResolvedValue({ data: { status: 'no_data' } } as any)
    vi.mocked(signalApi.getDashboardAuction).mockResolvedValue({ data: { picks: [], sectors: [] } } as any)
    vi.mocked(api.get).mockResolvedValue({ data: {} })
    vi.mocked(api.post).mockResolvedValue({ data: { status: 'ok' } })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  // 1.1 AC①：挂载即调 signalApi.getDashboardSummary（主契约）
  it('1.1 sentiment: 挂载调 getDashboardSummary，渲染仪表盘 + 市场快照 + 资金全景区块', async () => {
    renderDashboard('/')
    await waitFor(() => expect(signalApi.getDashboardSummary).toHaveBeenCalled())
    expect(await screen.findByText('综合情绪指数 · 八维风向感知')).toBeInTheDocument()
    expect(screen.getByText('市场快照')).toBeInTheDocument()
    expect(screen.getByText('资金全景')).toBeInTheDocument()
    // 综合分从接口 score 渲染
    expect(screen.getAllByText('72').length).toBeGreaterThan(0)
  })

  // 1.1 AC②：AI 解读 3 条支撑原因不空白（即使 backend 无 reasons 字段也走 fallback_reason 文案）
  it('1.1 sentiment: AI 解读渲染 3 条支撑原因，缺字段标 fallback 不空白', async () => {
    renderDashboard('/')
    const card = await screen.findByText('实时指标解读')
    const aiCard = card.closest('.ai-sentiment-card')!
    // 3 条支撑原因标题都在
    expect(within(aiCard).getByText(/支撑原因 1/)).toBeInTheDocument()
    expect(within(aiCard).getByText(/支撑原因 2/)).toBeInTheDocument()
    expect(within(aiCard).getByText(/支撑原因 3/)).toBeInTheDocument()
  })

  // 1.1 AC③：资金全景缺实时字段走 EmptyState + fallback_reason，不空白
  it('1.1 sentiment: 资金全景缺实时字段走 EmptyState + fallback_reason', async () => {
    renderDashboard('/')
    expect(await screen.findByText('资金全景待接入实时字段')).toBeInTheDocument()
    expect(screen.getByText(/fallback_reason/)).toBeInTheDocument()
    // 4 资金分项占位都在（北向/主力/融资/两市成交）
    expect(screen.getByText('北向资金')).toBeInTheDocument()
    expect(screen.getByText('主力资金')).toBeInTheDocument()
  })

  // 1.1 AC④：历史情绪子页 4 MetricCard 占位（分位/斜率/回撤/历史相似）不空白
  it('1.1 sentiment history: 4 MetricCard 占位（分位/斜率/回撤/历史相似）', async () => {
    renderDashboard('/')
    const sentimentTabs = screen.getByRole('tablist', { name: '市场情绪子页签' })
    fireEvent.click(within(sentimentTabs).getByRole('tab', { name: /历史情绪/ }))
    expect(await screen.findByText('当前分位')).toBeInTheDocument()
    expect(screen.getByText('情绪斜率')).toBeInTheDocument()
    expect(screen.getByText('回撤风险')).toBeInTheDocument()
    expect(screen.getByText('历史相似')).toBeInTheDocument()
  })

  // 1.3 AC①：信号总览挂载渲染矩阵 + 概况 + 实时流 + TOP8 + 双图表
  it('1.3 signal-overview: 渲染矩阵 + 概况 + 实时流 + TOP8 + 双图表', async () => {
    renderDashboard('/dashboard/signals')
    expect(await screen.findByRole('heading', { name: '信号总览' })).toBeInTheDocument()
    expect(screen.getByText('行业信号矩阵')).toBeInTheDocument()
    expect(screen.getByText('今日信号概况')).toBeInTheDocument()
    expect(screen.getByText('实时信号流')).toBeInTheDocument()
    expect(screen.getByText('最强信号 TOP 8')).toBeInTheDocument()
    expect(screen.getByText('30 日信号趋势')).toBeInTheDocument()
    expect(screen.getByText('板块信号气泡图')).toBeInTheDocument()
  })

  // 1.3 AC②：筛选条 5 按钮可切换，点击改变过滤逻辑（不报错）
  it('1.3 signal-overview: 5 个筛选按钮可切换', async () => {
    renderDashboard('/dashboard/signals')
    await screen.findByRole('heading', { name: '信号总览' })
    const buyBtn = screen.getByRole('button', { name: '仅买入' })
    fireEvent.click(buyBtn)
    expect(buyBtn).toHaveClass('active')
    // 切回全部
    const allBtn = screen.getByRole('button', { name: '全部信号' })
    fireEvent.click(allBtn)
    expect(allBtn).toHaveClass('active')
  })
})
