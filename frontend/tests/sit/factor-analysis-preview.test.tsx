import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Screener from '../../src/pages/Screener'
import { screenerApi, signalApi } from '../../src/api/client'

// SIT scope：Screener 3.3 factor-analysis preview —— 引导条 + IC 柱图（ECharts）+
// IC/ICIR 统计表 + 相关性热力图（ECharts）+ 分层收益 + 行业暴露。断言 mode 专属渲染 + 缺数据 EmptyState。
// API client 走 vi.mock（既有 Screener.test.tsx 同款）；factors tab mount 自动触发模型对比累积 factor_breakdown。

// ECharts option 透传出来便于断言 mode 专属图表类型（bar / heatmap）
vi.mock('echarts-for-react', () => ({
  default: ({ option }: any) => (
    <div
      data-testid="echarts-mock"
      data-chart-type={option?.series?.[0]?.type}
      data-series-count={option?.series?.length}
    />
  ),
}))
vi.mock('echarts', () => ({
  init: vi.fn(() => ({
    setOption: vi.fn(),
    on: vi.fn(),
    resize: vi.fn(),
    clear: vi.fn(),
    dispose: vi.fn(),
  })),
}))

vi.mock('../../src/api/client', () => ({
  screenerApi: {
    getModes: vi.fn(),
    run: vi.fn(),
    recordCandidatePool: vi.fn(),
    queryCandidatePool: vi.fn(),
    addWatchlist: vi.fn(),
    listWatchlist: vi.fn(),
  },
  signalApi: { triggerSync: vi.fn() },
  strategyApi: { createPlan: vi.fn(), addPicks: vi.fn() },
}))

// 多只候选股带丰富 factor_breakdown，供 IC/ICIR/热力图/分层/行业派生
const FACTOR_PICKS = [
  { code: '300750', name: '宁德时代', price: 235.5, change_pct: 4.2, score: 88, grade: 'S', industry: '新能源',
    entry_reason: '秋神盘后龙头；竞价强', factor_breakdown: { technical: 8, money_flow: 6, fundamental: 3 } },
  { code: '688981', name: '中芯国际', price: 68.3, change_pct: 2.1, score: 82, grade: 'A', industry: '半导体',
    entry_reason: '秋神盘后龙头；半导体共振', factor_breakdown: { technical: 7, money_flow: 5, fundamental: 2 } },
  { code: '002594', name: '比亚迪', price: 312, change_pct: 1.8, score: 76, grade: 'A', industry: '新能源',
    entry_reason: '秋神盘后龙头；链共振', factor_breakdown: { technical: 6, money_flow: 4, fundamental: 5 } },
]

function mockRunForMode(modeId: string) {
  const base = { trade_date: '2026-06-26', data_freshness: { source: 'daily_kline', as_of: '2026-06-26' }, total_scored: 3, total_excluded: 0, elapsed: 0.1 }
  if (modeId === 'leader_scalp') return { data: { ...base, picks: FACTOR_PICKS } }
  return { data: { ...base, picks: [] } }
}

function renderFactors() {
  return render(
    <MemoryRouter initialEntries={['/screener/factors']}>
      <Screener />
    </MemoryRouter>,
  )
}

describe('Screener 3.3 factor-analysis preview SIT', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.setSystemTime(new Date('2026-07-02T10:00:00+08:00'))
    vi.clearAllMocks()
    vi.mocked(screenerApi.getModes).mockResolvedValue({
      data: {
        modes: [],
        total: 0,
        latest_trade_date: '2026-06-26',
        latest_dates: { daily_kline: '2026-06-26' },
        data_freshness: { status: 'fresh', as_of: '2026-06-26', source: 'daily_kline', quality_score: 96 },
      },
    } as any)
    vi.mocked(screenerApi.run).mockImplementation(((mode: string) => Promise.resolve(mockRunForMode(mode))) as any)
    vi.mocked(signalApi.triggerSync).mockResolvedValue({ data: { status: 'ok' } } as any)
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

  it('renders guide bar with 4-step usage flow', async () => {
    renderFactors()

    await waitFor(() => {
      expect(screen.getByText('怎么用:')).toBeInTheDocument()
    })
    expect(screen.getByText(/看IC柱状图找有效因子/)).toBeInTheDocument()
    expect(screen.getByText(/看热力图去冗余/)).toBeInTheDocument()
  })

  it('renders IC bar chart (ECharts bar) + IC/ICIR stats table after picks load', async () => {
    renderFactors()

    await waitFor(() => {
      expect(screenerApi.run).toHaveBeenCalledWith('leader_scalp', expect.any(Number), expect.any(String))
    })

    // IC 分析 card
    await waitFor(() => {
      expect(screen.getByText('因子 IC 分析')).toBeInTheDocument()
    })
    // IC 柱图渲染（ECharts bar；柱图 + 热力图都有 testid，用 getAllByTestId 取 bar）
    await waitFor(() => {
      const charts = screen.getAllByTestId('echarts-mock')
      const barChart = charts.find(c => c.getAttribute('data-chart-type') === 'bar')
      expect(barChart).toBeDefined()
    })

    // IC/ICIR 统计表头
    expect(screen.getByText('IC / ICIR 统计')).toBeInTheDocument()
    expect(screen.getByText('ICIR')).toBeInTheDocument()
    expect(screen.getByText('t-stat')).toBeInTheDocument()
    // 因子 label（来自 factor_breakdown 的中文映射）
    await waitFor(() => {
      expect(screen.getAllByText('技术面').length).toBeGreaterThan(0)
    })
  })

  it('renders correlation heatmap (ECharts heatmap) with factor matrix', async () => {
    renderFactors()

    await waitFor(() => {
      expect(screen.getAllByTestId('echarts-mock').length).toBeGreaterThanOrEqual(1)
    })

    // 相关性矩阵 card
    await waitFor(() => {
      expect(screen.getByText('因子相关性矩阵')).toBeInTheDocument()
    })
    // 热力图渲染（ECharts heatmap）—— 第二个 echarts-mock 应是 heatmap
    const charts = screen.getAllByTestId('echarts-mock')
    const heatChart = charts.find(c => c.getAttribute('data-chart-type') === 'heatmap')
    expect(heatChart).toBeDefined()
  })

  it('renders decile return table with D1..D10 tiers + long-short spread row', async () => {
    renderFactors()

    await waitFor(() => {
      expect(screen.getByText('因子收益率分层')).toBeInTheDocument()
    })
    expect(screen.getByText('累计收益')).toBeInTheDocument()
    // 多-空对冲 summary row
    await waitFor(() => {
      expect(screen.getByText('多-空对冲')).toBeInTheDocument()
    })
  })

  it('renders industry exposure table with high/mid/low tags', async () => {
    renderFactors()

    await waitFor(() => {
      expect(screen.getByText('行业因子暴露')).toBeInTheDocument()
    })
    expect(screen.getByText('暴露程度')).toBeInTheDocument()
    // 行业名（新能源 / 半导体 来自 picks.industry）
    await waitFor(() => {
      expect(screen.getAllByText('新能源').length).toBeGreaterThan(0)
      expect(screen.getAllByText('半导体').length).toBeGreaterThan(0)
    })
    // 暴露 tag（偏高/偏低/中性之一）
    const tags = screen.getAllByText(/^(偏高|偏低|中性)$/)
    expect(tags.length).toBeGreaterThan(0)
  })

  it('shows footer with ICIR definition', async () => {
    renderFactors()

    await waitFor(() => {
      expect(screen.getByText(/ICIR = IC均值\/IC标准差/)).toBeInTheDocument()
    })
  })

  it('renders EmptyState when no picks (no factor data)', async () => {
    vi.mocked(screenerApi.run).mockResolvedValue({
      data: { trade_date: '2026-06-26', picks: [], total_scored: 0, total_excluded: 0, elapsed: 0.1 },
    } as any)

    renderFactors()

    await waitFor(() => {
      const fallback = screen.queryByText(/暂无因子 IC 数据/) ||
        screen.queryByText(/后端未返回因子统计/) ||
        screen.queryByText(/候选股缺少行业字段/)
      expect(fallback).not.toBeNull()
    })
  })
})
