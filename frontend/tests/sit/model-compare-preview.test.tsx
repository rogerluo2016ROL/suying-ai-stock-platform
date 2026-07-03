import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Screener from '../../src/pages/Screener'
import { screenerApi, signalApi } from '../../src/api/client'

// SIT scope：Screener 3.2 model-compare preview —— 模型选择器 + 共识统计条 +
// 共识矩阵（星级 + 模型 chip）+ 跨模型评分卡（指标条）。断言 mode 专属渲染 + token 化 + 缺数据 EmptyState。
// API client 走 vi.mock（既有 Screener.test.tsx 同款）；models tab mount 自动触发 4 模型 run。

vi.mock('echarts-for-react', () => ({
  default: ({ option }: any) => (
    <div data-testid="echarts-mock" data-chart-type={option?.series?.[0]?.type} />
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

// 模型对比 run 返回：leader_scalp 选宁德时代+中芯国际；bi_trend_full_market 也选宁德时代 → 共识
function mockRunForMode(modeId: string) {
  const base = { trade_date: '2026-06-26', data_freshness: { source: 'daily_kline', as_of: '2026-06-26' }, total_scored: 1, total_excluded: 0, elapsed: 0.1 }
  if (modeId === 'leader_scalp') {
    return { data: { ...base, picks: [
      { code: '300750', name: '宁德时代', price: 235.5, change_pct: 4.2, score: 85, grade: 'S', entry_reason: '秋神盘后龙头；竞价强', factor_breakdown: { technical: 8, money_flow: 6 } },
      { code: '688981', name: '中芯国际', price: 68.3, change_pct: 2.1, score: 80, grade: 'A', entry_reason: '秋神盘后龙头；半导体共振', factor_breakdown: { technical: 6 } },
    ] } }
  }
  if (modeId === 'bi_trend_full_market') {
    return { data: { ...base, picks: [
      { code: '300750', name: '宁德时代', price: 235.5, change_pct: 4.2, score: 78, grade: 'A', entry_reason: '毕师傅全市场 V1.0；硬科技', factor_breakdown: { hard_tech_conviction: 5, ignition_power: 3 } },
    ] } }
  }
  // leader_closing / leader_intraday 返回空，凑出"部分模型无候选"的 stats 步骤
  return { data: { ...base, picks: [] } }
}

function renderModels() {
  return render(
    <MemoryRouter initialEntries={['/screener/models']}>
      <Screener />
    </MemoryRouter>,
  )
}

describe('Screener 3.2 model-compare preview SIT', () => {
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
    vi.mocked(screenerApi.recordCandidatePool).mockResolvedValue({
      data: { pool_id: 'POOL-compare-2026-06-26', id: 9, created_at: '2026-06-26T15:00:00Z' },
    } as any)
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

  it('renders model selector with 4 model chips + run state badge', async () => {
    renderModels()

    await waitFor(() => {
      expect(screenerApi.run).toHaveBeenCalledWith('leader_scalp', expect.any(Number), expect.any(String))
    })

    // 4 模型简称 chip（毕/秋/秋/毕）
    const chips = screen.getAllByText(/^(毕|秋)$/).filter(el => el.classList.contains('model-chip'))
    expect(chips.length).toBeGreaterThanOrEqual(1)
    // 运行完成徽标
    await waitFor(() => {
      expect(screen.getByText(/已完成/)).toBeInTheDocument()
    })
  })

  it('renders consensus matrix with star ratings + model chips for cross-model consensus', async () => {
    renderModels()

    await waitFor(() => {
      expect(screenerApi.run).toHaveBeenCalledWith('leader_scalp', expect.any(Number), expect.any(String))
    })

    // 共识矩阵标题 + 共识只数
    await waitFor(() => {
      expect(screen.getByText(/共识矩阵/)).toBeInTheDocument()
    })
    // 宁德时代被 2 个模型选中（秋 + 毕）→ 出现在矩阵 + 评分卡（多处，用 getAllByText）
    await waitFor(() => {
      const occurrences = screen.getAllByText('宁德时代')
      expect(occurrences.length).toBeGreaterThanOrEqual(1)
    })
    // 共识只数 meta（300750 + 688981 = 2 unique）
    expect(screen.getByText(/共 2 只标的/)).toBeInTheDocument()
  })

  it('clicking a consensus row reveals cross-model score cards with indicator bars', async () => {
    renderModels()

    await waitFor(() => {
      expect(screen.getAllByText('宁德时代').length).toBeGreaterThanOrEqual(1)
    })

    // 跨模型评分对比卡（默认选中第一个共识行）
    expect(screen.getByText('跨模型评分对比')).toBeInTheDocument()
    // 指标条 label（技术面/硬科技等来自 factor_breakdown）
    await waitFor(() => {
      const labels = screen.getAllByText(/^(技术面|硬科技|资金面)$/)
      expect(labels.length).toBeGreaterThan(0)
    })
  })

  it('stats bar shows per-model step counts + consensus rate', async () => {
    renderModels()

    await waitFor(() => {
      expect(screen.getAllByText('宁德时代').length).toBeGreaterThanOrEqual(1)
    })

    // 最终共识率文案
    expect(screen.getByText(/最终共识率/)).toBeInTheDocument()
    // 步骤只数（leader_scalp 2只；多处出现用 getAllByText）
    expect(screen.getAllByText('2只').length).toBeGreaterThan(0)
  })

  it('加入候选池 button calls recordCandidatePool with starred candidates', async () => {
    renderModels()

    await waitFor(() => {
      expect(screen.getAllByText('宁德时代').length).toBeGreaterThanOrEqual(1)
    })

    const addBtn = await screen.findByRole('button', { name: /加入候选池/ })
    fireEvent.click(addBtn)

    await waitFor(() => {
      expect(screenerApi.recordCandidatePool).toHaveBeenCalledTimes(1)
    })
    const payload = vi.mocked(screenerApi.recordCandidatePool).mock.calls[0][0]
    expect(payload.source_mode).toBe('model_compare')
    expect(payload.candidates.length).toBeGreaterThan(0)
    expect(payload.candidates[0]).toMatchObject({ code: '300750', name: '宁德时代' })
  })

  it('shows footer-bar with data source attribution', async () => {
    renderModels()

    await waitFor(() => {
      expect(screen.getAllByText('宁德时代').length).toBeGreaterThanOrEqual(1)
    })

    expect(screen.getByText(/数据来源: screener-service POST/)).toBeInTheDocument()
    expect(screen.getByText(/毕=毕师傅/)).toBeInTheDocument()
  })

  it('renders EmptyState fallback when no model returns any pick', async () => {
    vi.mocked(screenerApi.run).mockResolvedValue({
      data: { trade_date: '2026-06-26', picks: [], total_scored: 0, total_excluded: 0, elapsed: 0.1 },
    } as any)

    renderModels()

    // 无候选时回退文案（modelCompareMessage 或空矩阵提示）
    await waitFor(() => {
      const fallback = screen.queryByText(/模型已运行，但当前没有候选股票/) ||
        screen.queryByText(/模型对比未返回可用结果/) ||
        screen.queryByText(/等待可用候选/)
      expect(fallback).not.toBeNull()
    })
  })
})
