import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ConfigProvider, message } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { MemoryRouter } from 'react-router-dom'
import Screener from '../pages/Screener'
import { backtestApi, screenerApi, signalApi } from '../api/client'
import { FactorEvidencePanel } from '../pages/screener/FactorEvidencePanel'
import { toFactorEvidenceView } from '../pages/screener/factorEvidence'

vi.mock('../api/client', () => ({
  screenerApi: {
    getModes: vi.fn(),
    run: vi.fn(),
    recordCandidatePool: vi.fn(),
    queryCandidatePool: vi.fn(),
    addWatchlist: vi.fn(),
    listWatchlist: vi.fn(),
  },
  signalApi: {
    triggerSync: vi.fn(),
  },
  strategyApi: {
    createPlan: vi.fn(),
    addPicks: vi.fn(),
  },
  backtestApi: {
    getFactorEvidence: vi.fn(),
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

function factorMetric(overrides: Record<string, unknown> = {}) {
  return {
    factor: 'technical',
    label: '技术面',
    ic_mean: 0.04,
    ic_std: 0.02,
    icir: 2,
    t_stat: 3.2,
    observations: 20,
    ...overrides,
  }
}

function correlationCell(overrides: Record<string, unknown> = {}) {
  return {
    factor_x: 'technical',
    factor_y: 'fundamental',
    correlation: 0.3,
    observations: 20,
    ...overrides,
  }
}

function decileMetric(overrides: Record<string, unknown> = {}) {
  return {
    decile: 'D10',
    description: '最高分位',
    cumulative_return_pct: 4.1,
    daily_return_pct: 0.16,
    observations: 20,
    ...overrides,
  }
}

function readyFactorEvidence(overrides: Record<string, unknown> = {}) {
  return {
    status: 'ready',
    observations: 20,
    trade_dates: 5,
    factors: [factorMetric()],
    correlations: [correlationCell()],
    deciles: [decileMetric()],
    missing_requirements: [],
    ...overrides,
  }
}

describe('Screener', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.setSystemTime(new Date('2026-07-02T10:00:00+08:00'))
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
    vi.mocked(screenerApi.recordCandidatePool).mockResolvedValue({
      data: { pool_id: 'POOL-leader_scalp-2026-06-26', id: 7, created_at: '2026-06-26T15:00:00Z' },
    } as any)
    vi.mocked(screenerApi.queryCandidatePool).mockResolvedValue({
      data: { total: 1, page: 1, page_size: 20, records: [] },
    } as any)
    vi.mocked(screenerApi.addWatchlist).mockResolvedValue({
      data: { record: { id: 1, code: '002281', name: '光迅科技', sort_order: 0 } },
    } as any)
    vi.mocked(screenerApi.listWatchlist).mockResolvedValue({
      data: { total: 1, page: 1, page_size: 20, records: [] },
    } as any)
  })

  afterEach(() => {
    vi.useRealTimers()
    message.destroy()
  })

  it('shows Bi trend hard-tech track, reason, and four-axis flags', async () => {
    renderScreener()

    fireEvent.change(await screen.findByLabelText('选股日期'), { target: { value: '2026-06-26' } })
    fireEvent.change(screen.getByLabelText('Top 数量'), { target: { value: '30' } })
    fireEvent.click(screen.getByRole('button', { name: /开始选股/ }))

    expect(await screen.findByText('光迅科技')).toBeInTheDocument()
    await waitFor(() => {
      expect(signalApi.triggerSync).toHaveBeenCalledWith('daily_kline', 30)
      expect(screenerApi.run).toHaveBeenCalledWith('leader_scalp', 30, '2026-06-26')
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

  it('writes selected picks to the candidate pool via recordCandidatePool on button click', async () => {
    renderScreener()

    fireEvent.change(await screen.findByLabelText('选股日期'), { target: { value: '2026-06-26' } })
    fireEvent.click(screen.getByRole('button', { name: /开始选股/ }))

    expect(await screen.findByText('光迅科技')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /^加入候选池 →$/ }))

    await waitFor(() => {
      expect(screenerApi.recordCandidatePool).toHaveBeenCalledTimes(1)
    })
    const payload = vi.mocked(screenerApi.recordCandidatePool).mock.calls[0][0]
    expect(payload.source_module).toBe('screener')
    expect(payload.source_mode).toBe('leader_scalp')
    expect(payload.name).toContain('leader_scalp')
    expect(payload.candidates).toHaveLength(1)
    expect(payload.candidates[0]).toMatchObject({
      code: '002281',
      name: '光迅科技',
      score: 86,
      grade: 'S',
      rank: 1,
    })
  })

  it('DEF-1: 加入自选 button calls screenerApi.addWatchlist with first selected pick', async () => {
    renderScreener()

    fireEvent.change(await screen.findByLabelText('选股日期'), { target: { value: '2026-06-26' } })
    fireEvent.click(screen.getByRole('button', { name: /开始选股/ }))
    expect(await screen.findByText('光迅科技')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /^加入自选$/ }))

    await waitFor(() => {
      expect(screenerApi.addWatchlist).toHaveBeenCalledTimes(1)
    })
    expect(vi.mocked(screenerApi.addWatchlist).mock.calls[0][0]).toMatchObject({
      code: '002281',
      name: '光迅科技',
    })
    // 刷新侧栏（失败不阻断）
    expect(screenerApi.listWatchlist).toHaveBeenCalled()
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
    expect(await screen.findByLabelText('选股日期')).toHaveValue('2026-07-02')
    expect(screen.getByLabelText('Top 数量')).toHaveValue('20')
    expect(screen.getByRole('button', { name: /运行选股/ })).toBeInTheDocument()
    expect(screen.getByText('数据更新')).toBeInTheDocument()
    expect(screen.getByText('模型选股')).toBeInTheDocument()
    expect(screen.getByText('输出股票')).toBeInTheDocument()
    expect(screen.getByText('市值(亿)')).toBeInTheDocument()
    expect(screen.getByText(/模型: .*leader_scalp/)).toBeInTheDocument()
    expect(screen.getByText('秋神盘后龙头分析')).toBeInTheDocument()
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

    expect(await screen.findByDisplayValue('2026-07-02')).toBeInTheDocument()
    expect(await screen.findByText('交易日：2026-07-02')).toBeInTheDocument()
    expect(screen.getByText('来源：默认当天')).toBeInTheDocument()
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
      expect(screenerApi.run).toHaveBeenCalledWith('leader_scalp', 20, '2026-06-26')
    })
    expect(await screen.findByText('交易日：2026-06-29')).toBeInTheDocument()
    expect(await screen.findByText('上海贝岭')).toBeInTheDocument()
  })

  it('does not derive IC or returns from pick scores', async () => {
    vi.mocked(screenerApi.run).mockResolvedValue({
      data: { picks: [{ code: '600000', score: 88, factor_breakdown: { technical: 9 } }] },
    } as never)
    vi.mocked(backtestApi.getFactorEvidence).mockResolvedValue({
      data: {
        status: 'insufficient_data',
        observations: 0,
        missing_requirements: ['future_returns'],
      },
    } as never)

    renderScreener('/screener/factors')

    expect(await screen.findByText('暂无真实因子回测数据')).toBeInTheDocument()
    expect(screen.queryByText('IC Mean')).not.toBeInTheDocument()
    expect(screen.queryByText('多-空对冲')).not.toBeInTheDocument()
  })

  it('keeps the factor page available when the evidence request fails', async () => {
    vi.mocked(backtestApi.getFactorEvidence).mockRejectedValueOnce(new Error('network unavailable'))

    renderScreener('/screener/factors')

    expect(await screen.findByText('真实因子回测数据暂不可用')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '智能选股 - 因子分析' })).toBeInTheDocument()
    expect(screen.queryByText('IC Mean')).not.toBeInTheDocument()
  })

  it.each([
    ['empty response', undefined],
    ['unknown status', { ...readyFactorEvidence(), status: 'unexpected' }],
    ['ready with zero observations', readyFactorEvidence({ observations: 0 })],
    ['ready with fractional observations', readyFactorEvidence({ observations: 1.5 })],
    ['ready without trade_dates', (() => {
      const { trade_dates: _tradeDates, ...response } = readyFactorEvidence()
      return response
    })()],
    ['ready with negative trade_dates', readyFactorEvidence({ trade_dates: -1 })],
    ['ready with fractional trade_dates', readyFactorEvidence({ trade_dates: 1.5 })],
    ['missing factors array', readyFactorEvidence({ factors: undefined })],
    ['non-array correlations', readyFactorEvidence({ correlations: {} })],
    ['non-array deciles', readyFactorEvidence({ deciles: null })],
    ['malformed factor metric', readyFactorEvidence({
      factors: [factorMetric({ ic_mean: Number.NaN })],
    })],
    ['malformed correlation cell', readyFactorEvidence({
      correlations: [correlationCell({ correlation: Number.POSITIVE_INFINITY })],
    })],
    ['malformed decile metric', readyFactorEvidence({
      deciles: [decileMetric({ cumulative_return_pct: 'not-a-number' })],
    })],
    ['IC above one', readyFactorEvidence({
      factors: [factorMetric({ ic_mean: 1.01 })],
    })],
    ['IC below negative one', readyFactorEvidence({
      factors: [factorMetric({ ic_mean: -1.01 })],
    })],
    ['negative IC standard deviation', readyFactorEvidence({
      factors: [factorMetric({ ic_std: -0.01 })],
    })],
    ['non-finite ICIR', readyFactorEvidence({
      factors: [factorMetric({ icir: Number.POSITIVE_INFINITY })],
    })],
    ['non-finite t-stat', readyFactorEvidence({
      factors: [factorMetric({ t_stat: Number.NaN })],
    })],
    ['correlation above one', readyFactorEvidence({
      correlations: [correlationCell({ correlation: 1.01 })],
    })],
    ['correlation below negative one', readyFactorEvidence({
      correlations: [correlationCell({ correlation: -1.01 })],
    })],
    ['factor observations missing', readyFactorEvidence({
      factors: [factorMetric({ observations: undefined })],
    })],
    ['correlation observations not positive', readyFactorEvidence({
      correlations: [correlationCell({ observations: 0 })],
    })],
    ['decile observations not an integer', readyFactorEvidence({
      deciles: [decileMetric({ observations: 1.5 })],
    })],
  ])('fails closed for %s', (_caseName, response) => {
    expect(toFactorEvidenceView(response)).toMatchObject({ kind: 'unsupported' })
  })

  it('keeps a minimal insufficient_data response as insufficient', () => {
    expect(toFactorEvidenceView({
      status: 'insufficient_data',
      observations: 0,
      missing_requirements: ['future_returns'],
    })).toEqual({ kind: 'insufficient', reasons: ['future_returns'] })
  })

  it('accepts inclusive IC and correlation boundaries with valid observations', () => {
    const view = toFactorEvidenceView(readyFactorEvidence({
      factors: [factorMetric({ ic_mean: -1, ic_std: 0, icir: -2, t_stat: -3 })],
      correlations: [correlationCell({ correlation: 1 })],
    }))

    expect(view).toMatchObject({ kind: 'ready' })
  })

  it('fails closed when the evidence panel receives a malformed ready view', () => {
    render(
      <FactorEvidencePanel
        loading={false}
        view={{ kind: 'ready', factors: undefined, correlations: [], deciles: [] } as never}
      />,
    )

    expect(screen.getByText('真实因子回测数据暂不可用')).toBeInTheDocument()
    expect(screen.queryByText('IC Mean')).not.toBeInTheDocument()
  })

  it('does not trigger the page error boundary for a ready response with a missing array', async () => {
    vi.mocked(backtestApi.getFactorEvidence).mockResolvedValue({
      data: readyFactorEvidence({ factors: undefined }),
    } as never)

    renderScreener('/screener/factors')

    expect(await screen.findByText('真实因子回测数据暂不可用')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '智能选股 - 因子分析' })).toBeInTheDocument()
    expect(screen.queryByText('IC Mean')).not.toBeInTheDocument()
  })

  it('explains a zero-pick run instead of only showing an empty table', async () => {
    vi.mocked(screenerApi.run).mockResolvedValueOnce({
      data: {
        trade_date: '2026-06-26',
        data_freshness: { status: 'fresh', as_of: '2026-06-26', source: 'daily_kline', quality_score: 96 },
        picks: [],
        no_result_reason: '2026-07-01 未找到符合竞价 T+0 条件的触发股。常见原因是当日竞价/涨停数据未入库。',
        screening_trace: [
          { step: '交易日确认', status: 'ok', detail: '使用交易日 2026-07-01' },
          { step: '触发股筛选', status: 'empty', detail: '竞价触发股 0 只' },
          { step: '概念映射', status: 'skipped', detail: '有效概念 0 个' },
        ],
        rejection_summary: [
          { reason: '封单金额不足7亿', count: 3 },
        ],
        total_scored: 58,
        total_excluded: 58,
        elapsed: 0.1,
      },
    } as any)
    renderScreener()

    fireEvent.click(await screen.findByRole('button', { name: /运行选股/ }))

    expect(await screen.findByText('当前模型返回 0 只')).toBeInTheDocument()
    expect(screen.getAllByText(/未找到符合竞价 T\+0 条件的触发股/).length).toBeGreaterThan(0)
    expect(screen.getByText('选债过程')).toBeInTheDocument()
    expect(screen.getByText(/触发股筛选/)).toBeInTheDocument()
    expect(screen.getByText(/竞价触发股 0 只/)).toBeInTheDocument()
    expect(screen.getByText('封单金额不足7亿：3')).toBeInTheDocument()
  })
})
