import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { MemoryRouter } from 'react-router-dom'
import Dashboard from '../pages/Dashboard'
import api, { signalApi } from '../api/client'

vi.mock('../api/client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
  signalApi: {
    getDashboardSummary: vi.fn(),
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

function renderDashboard() {
  return render(
    <ConfigProvider locale={zhCN}>
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    </ConfigProvider>,
  )
}

async function findSmartDashboardTabs() {
  return waitFor(() => {
    const tablist = screen.getAllByRole('tablist').find(item => (
      within(item).queryByRole('tab', { name: '市场情绪' })
    ))
    expect(tablist).toBeTruthy()
    return tablist!
  })
}

describe('Dashboard', () => {
  beforeEach(() => {
    vi.mocked(signalApi.getDashboardSummary).mockResolvedValue({ data: dashboardSummary } as any)
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url.startsWith('/dashboard/summary')) {
        return Promise.resolve({ data: { status: 'no_data' } })
      }
      if (url === '/dashboard/auction') {
        return Promise.resolve({ data: { picks: [], sectors: [] } })
      }
      return Promise.resolve({ data: {} })
    })
    vi.mocked(api.post).mockResolvedValue({ data: { status: 'ok' } } as any)
  })

  it('groups market sentiment, auction intent, signal overview, and watchlist tracking as smart dashboard sub-tabs', async () => {
    renderDashboard()

    const dashboardTabs = await findSmartDashboardTabs()

    expect(within(dashboardTabs).getByRole('tab', { name: '市场情绪' })).toBeInTheDocument()
    expect(within(dashboardTabs).getByRole('tab', { name: '竞价意图' })).toBeInTheDocument()
    expect(within(dashboardTabs).getByRole('tab', { name: '信号总览' })).toBeInTheDocument()
    expect(within(dashboardTabs).getByRole('tab', { name: '自选跟踪' })).toBeInTheDocument()

    fireEvent.click(within(dashboardTabs).getByRole('tab', { name: '自选跟踪' }))
    expect(await screen.findByText('中际旭创')).toBeInTheDocument()
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
    expect(await screen.findByText('79.5')).toBeInTheDocument()
    expect(screen.getByText('[BULL] 牛市 - 积极做多')).toBeInTheDocument()

    fireEvent.click(within(dashboardTabs).getByRole('tab', { name: '信号总览' }))
    expect(await screen.findByText('暂无信号数据')).toBeInTheDocument()

    fireEvent.click(within(dashboardTabs).getByRole('tab', { name: '自选跟踪' }))
    expect(await screen.findByText('暂无自选股数据')).toBeInTheDocument()
  })
})
