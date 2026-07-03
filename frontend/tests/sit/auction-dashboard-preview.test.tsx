import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { MemoryRouter } from 'react-router-dom'
import Dashboard from '../../src/pages/Dashboard'
import { signalApi } from '../../src/api/client'

// SIT scope：Dashboard 1.2 auction-dashboard 竞价意图 preview 的 4 专属区块渲染对齐 +
// 缺数据 EmptyState。AC①专属渲染（撮合价走势/四维评分/一字定方向/全量明细）+ AC④EmptyState。
// signalApi.getDashboardAuction 提供 top_bullish/top_bearish；dashboard-summary 提供 auction_intent 统计。

vi.mock('echarts-for-react', () => ({
  default: ({ style }: { style?: React.CSSProperties }) => <div data-testid="mock-chart" style={style} />,
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
  market_sentiment: { score: 70, label: '偏牛', trade_date: '2026-06-25', avg_change_pct: 1.1, up_stocks: 1800, down_stocks: 1400, total_stocks: 3800 },
  signal_stocks: [],
  limit_stocks: { up_count: 50, down_count: 10, data_source: 'stk_limit' },
  alert_signals: [],
  auction_intent: {
    trade_date: '2026-06-25',
    total_analyzed: 24,
    strong_bullish_count: 3,
    moderate_bullish_count: 5,
    bullish_count: 8,
    moderate_bearish_count: 4,
    strong_bearish_count: 2,
    bearish_count: 6,
    neutral_count: 10,
    top_bullish: [
      { code: '300750', name: '宁德时代', chg_pct: 8.2, score: 92, price: 218.5, industry: '新能源', vol_ratio: 13.5, buy_sell_ratio: 1.4, reasons: ['竞价高开', '量能放大'] },
      { code: '688981', name: '中芯国际', chg_pct: 5.6, score: 85, price: 68.2, industry: '半导体', vol_ratio: 9.2, buy_sell_ratio: 1.1 },
    ],
    top_bearish: [
      { code: '600000', name: '浦发银行', chg_pct: -5.27, score: 18, price: 9.8, industry: '银行', vol_ratio: 15.2, buy_sell_ratio: 0.6 },
    ],
  },
  watchlist: [],
  data_sources: { signal_stocks: 'PG daily_kline' },
}

function renderDashboard(route = '/dashboard/auction') {
  return render(
    <ConfigProvider locale={zhCN}>
      <MemoryRouter initialEntries={[route]}>
        <Dashboard />
      </MemoryRouter>
    </ConfigProvider>,
  )
}

describe('Dashboard 1.2 auction-dashboard preview (SIT)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(signalApi.getDashboardSummary).mockResolvedValue({ data: dashboardSummary } as any)
    vi.mocked(signalApi.getScreeningDashboardSummary).mockResolvedValue({ data: dashboardSummary } as any)
    vi.mocked(signalApi.getDashboardAuction).mockResolvedValue({ data: { picks: [], sectors: [] } } as any)
  })
  afterEach(() => cleanup())

  it('renders the 4 preview-specific sections aligned to 1.2 (timeline/radar/sector/detail)', async () => {
    renderDashboard()

    expect(await screen.findByRole('heading', { name: '竞价意图' })).toBeInTheDocument()
    // AC①专属渲染（非通用壳）
    expect(screen.getByText('竞价撮合价走势')).toBeInTheDocument()
    expect(screen.getByText('四维评分')).toBeInTheDocument()
    expect(screen.getByText('一字定方向')).toBeInTheDocument()
    expect(screen.getByText('全量竞价明细')).toBeInTheDocument()
    // 选中个股信息卡（宁德时代，首只抢筹）
    expect(screen.getAllByText('宁德时代').length).toBeGreaterThan(0)
    // 一字定方向按行业聚合：新能源 + 半导体 + 银行（明细表行业列也会出现同名，用 getAllByText）
    expect(screen.getAllByText('新能源').length).toBeGreaterThan(0)
    expect(screen.getAllByText('半导体').length).toBeGreaterThan(0)
    expect(screen.getAllByText('银行').length).toBeGreaterThan(0)
    // 全量明细表头（信息卡 si-lbl 也含"竞价价"，用 getAllByText）
    expect(screen.getAllByText('竞价价').length).toBeGreaterThan(0)
    expect(screen.getAllByText('竞量比').length).toBeGreaterThan(0)
  })

  it('shows EmptyState when auction data is empty (no bullish/bearish rows)', async () => {
    vi.mocked(signalApi.getDashboardSummary).mockResolvedValue({
      data: { ...dashboardSummary, auction_intent: { trade_date: '2026-06-25', total_analyzed: 0, bullish_count: 0, bearish_count: 0 } },
    } as any)

    renderDashboard()

    // 一字定方向缺数据走 EmptyState（不空白）
    await waitFor(() => {
      expect(screen.getByText('暂无板块竞价数据')).toBeInTheDocument()
    })
    expect(screen.getByText('暂无竞价明细')).toBeInTheDocument()
  })

  it('calls signalApi.getDashboardSummary on mount (契约对账)', async () => {
    renderDashboard()

    await waitFor(() => {
      expect(signalApi.getDashboardSummary).toHaveBeenCalled()
    })
  })
})
