import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { MemoryRouter } from 'react-router-dom'
import Screener from '../pages/Screener'
import { screenerApi, signalApi } from '../api/client'

vi.mock('../api/client', () => ({
  screenerApi: {
    getModes: vi.fn(),
    run: vi.fn(),
  },
  signalApi: {
    triggerSync: vi.fn(),
  },
  strategyApi: {
    createPlan: vi.fn(),
    addPicks: vi.fn(),
  },
}))

function renderScreener(route = '/screener') {
  return render(
    <ConfigProvider locale={zhCN}>
      <MemoryRouter initialEntries={[route]}>
        <Screener />
      </MemoryRouter>
    </ConfigProvider>,
  )
}

describe('Screener', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(screenerApi.getModes).mockResolvedValue({
      data: {
        modes: [
          { id: 'bi_trend_launch', name: '毕师傅趋势启动', cycle: '短线' },
        ],
        total: 1,
        latest_trade_date: '2026-06-26',
        latest_dates: {
          daily_kline: '2026-06-26',
          stk_auction_o: '2026-06-26',
        },
        data_freshness: { status: 'fresh', as_of: '2026-06-26', source: 'daily_kline', quality_score: 96 },
      },
    } as any)
    vi.mocked(screenerApi.run).mockResolvedValue({
      data: {
        trade_date: '2026-06-26',
        data_freshness: { status: 'fresh', as_of: '2026-06-26', source: 'stk_auction_o', quality_score: 96 },
        market_env: 'neutral',
        total_scored: 1,
        total_excluded: 0,
        elapsed: 1.2,
        picks: [{
          code: '002281',
          name: '光迅科技',
          price: 88.5,
          score: 86,
          grade: 'S',
          signal: 'watch',
          hard_tech: {
            track: 'AI算力',
            tier: 'core',
            matched_keywords: ['算力', '芯片', '通信'],
            chokepoint_level: 'normal',
          },
          factor_breakdown: {
            startup_quality: -7,
            ignition_power: 0,
            hard_tech_conviction: 4,
          },
          entry_reason: '硬科技: AI算力(core)；风险: late_rebound、ma20_extension',
          risk_flags: ['late_rebound', 'ma20_extension'],
          power_flags: [],
        }],
      },
    } as any)
    vi.mocked(signalApi.triggerSync).mockResolvedValue({
      data: { status: 'ok' },
    } as any)
  })

  it('shows Bi trend hard-tech track, reason, and four-axis flags', async () => {
    renderScreener()

    fireEvent.change(await screen.findByLabelText('选股日期'), { target: { value: '2026-06-26' } })
    fireEvent.change(screen.getByLabelText('Top 数量'), { target: { value: '30' } })
    fireEvent.click(screen.getByRole('button', { name: /开始选股/ }))

    expect(await screen.findByText('光迅科技')).toBeInTheDocument()
    await waitFor(() => {
      expect(signalApi.triggerSync).toHaveBeenCalledWith('stk_auction_o', 1)
      expect(screenerApi.run).toHaveBeenCalledWith('leader_auction', 30, '2026-06-26')
    })
    expect(screen.getByText('AI算力')).toBeInTheDocument()
    expect(screen.getByText('core')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /展开四轴解释/ }))

    await waitFor(() => {
      expect(screen.getByText(/硬科技: AI算力/)).toBeInTheDocument()
    })
    expect(screen.getByText('late_rebound')).toBeInTheDocument()
    expect(screen.getByText('ma20_extension')).toBeInTheDocument()
    expect(screen.getByText('硬科技 4.0')).toBeInTheDocument()
    expect(screen.getByText('启动质量 -7.0')).toBeInTheDocument()
  })

  it('matches the screener workbench prototype structure', async () => {
    renderScreener()

    expect(screen.getByLabelText('模型分类页签')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /趋势 \/ 秋神/ })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /多因子 \/ 主题型/ })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /可转债/ })).toBeInTheDocument()
    expect(screen.getByText('秋神竞价超预期选股')).toBeInTheDocument()
    expect(screen.getByText('秋神午后选股模型')).toBeInTheDocument()
    expect(screen.getByText('毕师傅全市场 V1.0')).toBeInTheDocument()
    expect(screen.getByText('日期')).toBeInTheDocument()
    expect(await screen.findByLabelText('选股日期')).toHaveValue('2026-06-26')
    expect(screen.getByLabelText('Top 数量')).toHaveValue('20')
    expect(screen.getByRole('button', { name: /运行选股/ })).toBeInTheDocument()
    expect(screen.getByText('数据更新')).toBeInTheDocument()
    expect(screen.getByText('模型选股')).toBeInTheDocument()
    expect(screen.getByText('输出股票')).toBeInTheDocument()
    expect(screen.getByText('市值(亿)')).toBeInTheDocument()
    expect(screen.getByText('秋神竞价超预期分析')).toBeInTheDocument()
    expect(screen.getByText('等待模型输出')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '加入候选池 →' })).toBeInTheDocument()
  })

  it('initializes the date picker from the selected model data source', async () => {
    vi.mocked(screenerApi.getModes).mockResolvedValueOnce({
      data: {
        modes: [],
        total: 0,
        latest_trade_date: '2026-06-26',
        latest_dates: {
          daily_kline: '2026-06-26',
          stk_auction_o: '2026-06-29',
        },
        data_freshness: { status: 'fresh', as_of: '2026-06-26', source: 'daily_kline', quality_score: 96 },
      },
    } as any)

    renderScreener()

    expect(await screen.findByDisplayValue('2026-06-29')).toBeInTheDocument()
    expect(await screen.findByText('交易日：2026-06-29')).toBeInTheDocument()
    expect(screen.getByText('来源：stk_auction_o')).toBeInTheDocument()
  })

  it('shows the actual backend run date after model execution', async () => {
    vi.mocked(screenerApi.getModes).mockResolvedValueOnce({
      data: {
        modes: [],
        total: 0,
        latest_trade_date: '2026-06-26',
        latest_dates: {
          daily_kline: '2026-06-26',
          stk_auction_o: '2026-06-29',
        },
        data_freshness: { status: 'fresh', as_of: '2026-06-26', source: 'daily_kline', quality_score: 96 },
      },
    } as any)
    vi.mocked(screenerApi.run).mockResolvedValueOnce({
      data: {
        trade_date: '2026-06-29',
        data_freshness: { status: 'fresh', as_of: '2026-06-29', source: 'stk_auction_o', quality_score: 96 },
        picks: [
          { code: '600171', name: '上海贝岭', score: 88, grade: 'A', industry: '半导体', market_cap: 120 },
        ],
        total_scored: 1,
        total_excluded: 0,
        elapsed: 0.1,
      },
    } as any)
    renderScreener()

    fireEvent.click(await screen.findByRole('button', { name: /运行选股/ }))

    await waitFor(() => {
      expect(screenerApi.run).toHaveBeenCalledWith('leader_auction', 20, '2026-06-29')
    })
    expect(await screen.findByText('交易日：2026-06-29')).toBeInTheDocument()
    expect(await screen.findByText('上海贝岭')).toBeInTheDocument()
  })
})
