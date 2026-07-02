import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { MemoryRouter } from 'react-router-dom'
import Dashboard from '../pages/Dashboard'
import api, { signalApi } from '../api/client'

vi.mock('echarts-for-react', () => ({
  default: ({ className, style }: { className?: string; style?: React.CSSProperties }) => (
    <div data-testid="mock-chart" className={className} style={style} />
  ),
}))

vi.mock('../api/client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
  signalApi: {
    getDashboardSummary: vi.fn(),
    getScreeningDashboardSummary: vi.fn(),
    getDashboardAuction: vi.fn(),
  },
}))

const dashboardSummary = {
  refreshed_at: new Date().toISOString(),
  market_sentiment: {
    score: 66,
    label: '偏强',
    trade_date: '2026-06-25',
    avg_change_pct: 1.2,
    up_stocks: 3200,
    down_stocks: 1400,
    total_stocks: 5200,
    model: 'market breadth',
    formula: 'up/down + avg change',
    sub_dimensions: { breadth: 'strong' },
  },
  signal_stocks: [{
    code: '002354',
    name: '天娱数科',
    price: 42.97,
    change_pct: 3.2,
    volume: 10000,
    signal: 'Bullish',
    desc: '多头信号',
    market: 'SZ',
  }],
  limit_stocks: {
    up_count: 3,
    down_count: 1,
    up_list: [],
    down_list: [],
    data_source: 'stk_limit',
  },
  alert_signals: [{
    type: 'volume',
    icon: '!',
    level: 'warning',
    code: '002354',
    name: '天娱数科',
    price: 42.97,
    change_pct: 3.2,
    reason: '量价异动',
  }],
  auction_intent: {
    trade_date: '2026-06-25',
    total_analyzed: 20,
    bullish_count: 2,
    bearish_count: 1,
    neutral_count: 17,
    data_source: 'auction',
    top_bullish: [{
      code: '002354',
      name: '天娱数科',
      auction_price: 42.97,
      prev_close: 41.64,
      chg_pct: 3.2,
      vs_vwap: 1.2,
      vol_ratio: 2.4,
      open_gap: 3.2,
      vol: 12000,
      amount: 500000,
      intent: 'bullish',
      icon: '↑',
      level: 'strong',
      score: 82,
      reasons: ['高开放量'],
      breakdown: { price_direction: 20, buy_sell_pressure: 20, auction_strength: 22, opening_continuity: 20 },
    }],
    top_bearish: [],
  },
  service_health: [{ key: 'screener', name: '选股服务', port: 8001, online: true }],
  screener_modes: [],
  watchlist: [{ code: '300308', name: '中际旭创', market_cap: 120000000000, industry: '通信设备' }],
  data_sources: {
    signal_stocks: 'PG daily_kline',
    alert_signals: '量价异动',
    watchlist: 'PG stocks',
  },
}

function renderDashboard(initialRoute = '/') {
  return render(
    <ConfigProvider locale={zhCN}>
      <MemoryRouter initialEntries={[initialRoute]}>
        <Dashboard />
      </MemoryRouter>
    </ConfigProvider>,
  )
}

async function findSmartDashboardTabs() {
  return waitFor(() => {
    const tablist = screen.getAllByRole('tablist').find(item => (
      within(item).queryByRole('tab', { name: /市场情绪/ })
    ))
    expect(tablist).toBeTruthy()
    return tablist!
  })
}

describe('Dashboard', () => {
  beforeEach(() => {
    vi.mocked(signalApi.getDashboardSummary).mockResolvedValue({ data: dashboardSummary } as any)
    vi.mocked(signalApi.getScreeningDashboardSummary).mockResolvedValue({ data: { status: 'no_data' } } as any)
    vi.mocked(signalApi.getDashboardAuction).mockResolvedValue({ data: { picks: [], sectors: [] } } as any)
    vi.mocked(api.get).mockImplementation((url: string) => {
      return Promise.resolve({ data: {} })
    })
    vi.mocked(api.post).mockResolvedValue({ data: { status: 'ok' } } as any)
  })

  it('groups market sentiment, auction intent, signal overview, and watchlist tracking as smart dashboard sub-tabs', async () => {
    renderDashboard()

    const dashboardTabs = await findSmartDashboardTabs()

    expect(within(dashboardTabs).getByRole('tab', { name: /市场情绪/ })).toBeInTheDocument()
    expect(within(dashboardTabs).getByRole('tab', { name: /竞价意图/ })).toBeInTheDocument()
    expect(within(dashboardTabs).getByRole('tab', { name: /信号总览/ })).toBeInTheDocument()
    expect(within(dashboardTabs).getByRole('tab', { name: /自选跟踪/ })).toBeInTheDocument()

    fireEvent.click(within(dashboardTabs).getByRole('tab', { name: /自选跟踪/ }))
    expect((await screen.findAllByText('中际旭创')).length).toBeGreaterThan(0)
  })

  it('renders market sentiment as three dedicated sub-pages', async () => {
    renderDashboard()

    expect(await screen.findByRole('heading', { name: '市场情绪' })).toBeInTheDocument()
    const sentimentTabs = screen.getByRole('tablist', { name: '市场情绪子页签' })

    expect(within(sentimentTabs).getByRole('tab', { name: /今日市场/ })).toHaveAttribute('aria-selected', 'true')
    expect(within(sentimentTabs).getByRole('tab', { name: /历史情绪/ })).toBeInTheDocument()
    expect(within(sentimentTabs).getByRole('tab', { name: /板块共振/ })).toBeInTheDocument()
    expect(screen.getByText('综合情绪指数 · 八维风向感知')).toBeInTheDocument()
    expect(screen.getByText('市场快照')).toBeInTheDocument()
    expect(screen.queryByText('情绪历史趋势')).not.toBeInTheDocument()

    fireEvent.click(within(sentimentTabs).getByRole('tab', { name: /历史情绪/ }))
    expect(within(sentimentTabs).getByRole('tab', { name: /历史情绪/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('情绪历史趋势')).toBeInTheDocument()
    expect(screen.getByText('历史相似场景')).toBeInTheDocument()
    expect(screen.getByText('周期状态表')).toBeInTheDocument()
    expect(screen.queryByText('市场快照')).not.toBeInTheDocument()

    fireEvent.click(within(sentimentTabs).getByRole('tab', { name: /板块共振/ }))
    expect(within(sentimentTabs).getByRole('tab', { name: /板块共振/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('TOP 1')).toBeInTheDocument()
    expect(screen.getByText('板块共振热力图')).toBeInTheDocument()
    expect(screen.getByText('选中板块详情')).toBeInTheDocument()
    expect(screen.getByText('实时共振结论')).toBeInTheDocument()
    expect(screen.queryByText('综合情绪指数 · 八维风向感知')).not.toBeInTheDocument()
  })

  it('links sector cards to stock change details and opens the detail drawer', async () => {
    vi.mocked(signalApi.getDashboardSummary).mockResolvedValue({
      data: {
        ...dashboardSummary,
        signal_stocks: [
          { code: '688981', name: '中芯国际', price: 68.2, change_pct: 5.8, signal: 'Bullish', industry: '半导体', score: 88 },
          { code: '300750', name: '宁德时代', price: 218.5, change_pct: 8.2, signal: 'Bullish', industry: '新能源', score: 92 },
          { code: '300274', name: '阳光电源', price: 87.6, change_pct: 4.6, signal: 'Bullish', industry: '新能源', score: 81 },
        ],
      },
    } as any)

    renderDashboard()

    expect(await screen.findByRole('heading', { name: '市场情绪' })).toBeInTheDocument()
    const sentimentTabs = screen.getByRole('tablist', { name: '市场情绪子页签' })
    fireEvent.click(within(sentimentTabs).getByRole('tab', { name: /板块共振/ }))

    expect(await screen.findByText('中芯国际')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /TOP 2.*新能源 87/ }))

    expect(await screen.findByText('新能源 股票涨幅明细')).toBeInTheDocument()
    expect(screen.getAllByText('宁德时代').length).toBeGreaterThan(0)
    expect(screen.getAllByText('阳光电源').length).toBeGreaterThan(0)
    expect(screen.getAllByText('+8.20%').length).toBeGreaterThan(0)
    expect(screen.queryByText('中芯国际')).not.toBeInTheDocument()
  })

  it('uses real limit stock lists for sector drawer details', async () => {
    vi.mocked(signalApi.getDashboardSummary).mockResolvedValue({
      data: {
        ...dashboardSummary,
        signal_stocks: [],
        limit_stocks: {
          up_count: 2,
          down_count: 0,
          data_source: 'stk_limit',
          up_list: [
            { code: '688981', name: '中芯国际', price: 68.2, change_pct: 10.01, industry: '半导体', score: 86 },
            { code: '603986', name: '兆易创新', price: 86.35, change_pct: 9.98, industry: '半导体', score: 83 },
          ],
        },
      },
    } as any)

    renderDashboard()

    expect(await screen.findByRole('heading', { name: '市场情绪' })).toBeInTheDocument()
    const sentimentTabs = screen.getByRole('tablist', { name: '市场情绪子页签' })
    fireEvent.click(within(sentimentTabs).getByRole('tab', { name: /板块共振/ }))
    fireEvent.click(screen.getByRole('button', { name: /TOP 1.*半导体 85/ }))

    expect(await screen.findByText('半导体 股票涨幅明细')).toBeInTheDocument()
    expect(screen.getAllByText('中芯国际').length).toBeGreaterThan(0)
    expect(screen.getAllByText('兆易创新').length).toBeGreaterThan(0)
    expect(screen.getAllByText('+10.01%').length).toBeGreaterThan(0)
  })

  it('updates the side sector detail without opening drawer when clicking the heatmap', async () => {
    vi.mocked(signalApi.getDashboardSummary).mockResolvedValue({
      data: {
        ...dashboardSummary,
        signal_stocks: [
          { code: '300750', name: '宁德时代', price: 218.5, change_pct: 8.2, signal: 'Bullish', industry: '新能源', score: 92 },
        ],
      },
    } as any)

    renderDashboard()

    expect(await screen.findByRole('heading', { name: '市场情绪' })).toBeInTheDocument()
    const sentimentTabs = screen.getByRole('tablist', { name: '市场情绪子页签' })
    fireEvent.click(within(sentimentTabs).getByRole('tab', { name: /板块共振/ }))
    fireEvent.click(screen.getByRole('button', { name: /新能源 92 涨100%/ }))

    expect(await screen.findByRole('heading', { name: '新能源' })).toBeInTheDocument()
    expect(screen.getByText('宁德时代')).toBeInTheDocument()
    expect(screen.queryByText('新能源 股票涨幅明细')).not.toBeInTheDocument()
  })

  it('loads screening dashboard and auction data through the unified API facade', async () => {
    vi.mocked(signalApi.getScreeningDashboardSummary).mockResolvedValue({
      data: {
        status: 'ok',
        dual_consensus: [{ code: '300750', name: '宁德时代', consensus: 2, best_score: 92, best_grade: 'S', sources: ['trend', 'value'] }],
        merged: [],
        predictions: [{ code: '300750', name: '宁德时代', pred_return_pct: 8.2, current_price: 218.5 }],
        summary: { total_picks: 1, consensus_dual: 1, strategies_run: 2, predictions_total: 1, predictions_up: 1, predictions_down: 0 },
        elapsed: 18,
        date: '2026-06-27',
      },
    } as any)
    vi.mocked(signalApi.getDashboardAuction).mockResolvedValue({
      data: {
        picks: [{ code: '688981', name: '中芯国际', gap_pct: 5.8, score: 88, price: 68.2, industry: '半导体' }],
        sectors: [{ name: '半导体', count: 5 }],
      },
    } as any)

    renderDashboard()

    const dashboardTabs = await findSmartDashboardTabs()
    fireEvent.click(within(dashboardTabs).getByRole('tab', { name: /竞价意图/ }))
    expect(await screen.findByText('抢筹 TOP 10')).toBeInTheDocument()
    expect(screen.getByText('出货预警 TOP 10')).toBeInTheDocument()
    await waitFor(() => expect(screen.getAllByText('中芯国际').length).toBeGreaterThan(0))
    expect(signalApi.getScreeningDashboardSummary).toHaveBeenCalled()
    expect(signalApi.getDashboardAuction).toHaveBeenCalled()
    expect(api.get).not.toHaveBeenCalledWith(expect.stringContaining('/dashboard/summary'))
    expect(api.get).not.toHaveBeenCalledWith('/dashboard/auction')
  })

  it('renders auction intent as the full prototype dashboard, not a sparse candidate preview', async () => {
    vi.mocked(signalApi.getDashboardAuction).mockResolvedValue({
      data: {
        picks: [{ code: '300750', name: '宁德时代', chg_pct: 8.2, gap_pct: 8.2, score: 90, price: 218.5, industry: '新能源' }],
        sectors: [],
      },
    } as any)

    renderDashboard('/dashboard/auction')

    expect(await screen.findByRole('heading', { name: '竞价意图' })).toBeInTheDocument()
    expect(screen.getByText('交易日：2026-06-25')).toBeInTheDocument()
    expect(screen.getByText(/数据更新：/)).toBeInTheDocument()
    expect(screen.getByText('四维评分模型 · 撮合价走势 · 一字定方向 · 全量明细')).toBeInTheDocument()
    expect(screen.getByText('强烈抢筹')).toBeInTheDocument()
    expect(screen.getByText('偏多抢筹')).toBeInTheDocument()
    expect(screen.getByText('偏空出货')).toBeInTheDocument()
    expect(screen.getByText('强烈出货')).toBeInTheDocument()
    expect(screen.getByText('抢筹 TOP 10')).toBeInTheDocument()
    expect(screen.getByText('出货预警 TOP 10')).toBeInTheDocument()
    expect(screen.queryByText('竞价候选预览')).not.toBeInTheDocument()
  })

  it('renders signal overview as the full prototype matrix dashboard, not sparse empty lists', async () => {
    renderDashboard('/dashboard/signals')

    expect(await screen.findByRole('heading', { name: '信号总览' })).toBeInTheDocument()
    expect(screen.getByText('全市场六维信号扫描 · 板块共振 · 历史趋势')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '全部信号' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '仅买入' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '仅卖出' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '仅拐点' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '仅自选' })).toBeInTheDocument()
    expect(screen.getByText('今日信号概况')).toBeInTheDocument()
    expect(screen.getByText('实时信号流')).toBeInTheDocument()
    expect(screen.getByText('最强信号 TOP 8')).toBeInTheDocument()
    expect(screen.getByText('30 日信号趋势')).toBeInTheDocument()
    expect(screen.getByText('板块信号气泡图')).toBeInTheDocument()
    expect(screen.getByText('信号模型权重以后端返回为准；前端不展示固定权重。')).toBeInTheDocument()
    expect(screen.queryByText('今日交易信号')).not.toBeInTheDocument()
    expect(screen.queryByText('暂无信号数据')).not.toBeInTheDocument()
  })

  it('renders watchlist tracking with an honest empty state when backend watchlist is empty', async () => {
    vi.mocked(signalApi.getDashboardSummary).mockResolvedValue({
      data: {
        ...dashboardSummary,
        watchlist: [],
      },
    } as any)

    renderDashboard('/dashboard/watchlist')

    expect(await screen.findByRole('heading', { name: '自选跟踪' })).toBeInTheDocument()
    expect(screen.getByText('0 只自选 · 实时行情 · 信号监控 · 盈亏分析')).toBeInTheDocument()
    expect(screen.getByText('自选等权盈亏')).toBeInTheDocument()
    expect(screen.getByText('今日最强')).toBeInTheDocument()
    expect(screen.getByText('买入信号')).toBeInTheDocument()
    expect(screen.getByText('卖出/警报')).toBeInTheDocument()
    expect(screen.getByText('自选清单')).toBeInTheDocument()
    expect(screen.getByText('暂无自选股数据。')).toBeInTheDocument()
    expect(screen.getByText('行业分布')).toBeInTheDocument()
    expect(screen.getByText('盈亏贡献')).toBeInTheDocument()
    expect(screen.getByText('信号联动')).toBeInTheDocument()
  })

  it('renders market_regime_v2 and empty dashboard states without staying in loading copy', async () => {
    vi.mocked(signalApi.getDashboardSummary).mockResolvedValue({
      data: {
        ...dashboardSummary,
        market_sentiment: undefined,
        market_regime_v2: {
          regime: 'BULL',
          score: 79.5,
          confidence: 59,
          label: '[BULL] 牛市 - 积极做多',
          dimensions: {
            trend: { score: 150, weight: 0.25 },
            breadth: { score: 50, weight: 0.2 },
          },
        },
        signal_stocks: [],
        alert_signals: [],
        watchlist: [],
      },
    } as any)

    renderDashboard()

    const dashboardTabs = await findSmartDashboardTabs()
    await waitFor(() => expect(screen.getAllByText('79.5').length).toBeGreaterThan(0))
    expect(screen.getAllByText('[BULL] 牛市 - 积极做多').length).toBeGreaterThan(0)

    fireEvent.click(within(dashboardTabs).getByRole('tab', { name: /信号总览/ }))
    expect(await screen.findByText('今日信号概况')).toBeInTheDocument()
    expect(screen.getByText('行业信号矩阵')).toBeInTheDocument()
    expect(screen.getByText('暂无实时信号数据。')).toBeInTheDocument()

    fireEvent.click(within(dashboardTabs).getByRole('tab', { name: /自选跟踪/ }))
    expect(await screen.findByText('自选清单')).toBeInTheDocument()
    expect(screen.getByText('暂无自选股数据。')).toBeInTheDocument()
  })
})
