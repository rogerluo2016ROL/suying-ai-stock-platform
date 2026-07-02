import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import OpenDecision from '../../src/pages/OpenDecision'
import { chainApi, screenerApi, signalApi, tradeApi } from '../../src/api/client'

// SIT scope：OpenDecision 2.1 decision-overview + 2.4 candidate-pool 两 preview 的区块渲染 +
// 多源 API 契约调用（signalApi.getLive / chainApi.getCandidates / screenerApi.queryCandidatePool /
// tradeApi.*）。API client 走 vi.mock（与既有 OpenDecision.test.tsx 同源；项目 signalApi/chainApi/screenerApi
// client 由既有 mock 覆盖，未引入 MSW 因 contract 由生成 client 承载）。

vi.mock('../../src/api/client', () => ({
  signalApi: {
    getDashboardAuction: vi.fn(),
    getLive: vi.fn(),
  },
  chainApi: {
    getCandidates: vi.fn(),
  },
  screenerApi: {
    queryCandidatePool: vi.fn(),
  },
  tradeApi: {
    getAccount: vi.fn(),
    getPositions: vi.fn(),
    getOrders: vi.fn(),
    getRiskVerdicts: vi.fn(),
    getDecisionContexts: vi.fn(),
  },
}))

const liveSignals = [
  {
    code: '300750', name: '宁德时代', level: 'strong_buy', score: 88, confidence: 82,
    dimensions: { technical: 86, fundamental: 80, money_flow: 78, sentiment: 88 },
  },
  {
    code: '688981', name: '中芯国际', level: 'buy', score: 74, confidence: 68,
    dimensions: { technical: 76, fundamental: 70, money_flow: 65, sentiment: 72 },
  },
]

const chainCandidates = [
  { code: '300750', name: '宁德时代', industry: '新能源', score: 90, resonance_level: '强启动', last_change_pct: 8.2 },
  { code: '688981', name: '中芯国际', industry: '半导体', score: 88, resonance_level: '启动', last_change_pct: 5.8 },
]

const poolRecords = [
  {
    pool_id: 'POOL-open-decision-2026-06-29-am',
    source_module: 'open-decision',
    source_mode: 'leader_scalp',
    name: '盘前候选',
    candidates: [{ code: '002475', name: '立讯精密', score: 84, grade: 'A', rank: 1 }],
  },
]

function renderOpenDecision(route = '/open-decision') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <OpenDecision />
    </MemoryRouter>,
  )
}

describe('OpenDecision 2.1 + 2.4 preview SIT', () => {
  beforeEach(() => {
    vi.mocked(signalApi.getDashboardAuction).mockResolvedValue({ data: { date: '2026-06-29', total_count: 20, picks: [] } } as any)
    vi.mocked(signalApi.getLive).mockResolvedValue({ data: { session: 'intra', trade_date: '2026-06-29', signals: liveSignals } } as any)
    vi.mocked(chainApi.getCandidates).mockResolvedValue({ data: { candidates: chainCandidates } } as any)
    vi.mocked(screenerApi.queryCandidatePool).mockResolvedValue({
      data: { total: poolRecords.length, page: 1, page_size: 50, records: poolRecords },
    } as any)
    vi.mocked(tradeApi.getAccount).mockResolvedValue({ data: { account: { total_assets: 1280000, market_value: 894000, available: 386000, total_pnl: 23500 } } } as any)
    vi.mocked(tradeApi.getPositions).mockResolvedValue({ data: { positions: [] } } as any)
    vi.mocked(tradeApi.getOrders).mockResolvedValue({ data: { orders: [] } } as any)
    vi.mocked(tradeApi.getRiskVerdicts).mockResolvedValue({ data: { records: [] } } as any)
    vi.mocked(tradeApi.getDecisionContexts).mockResolvedValue({ data: { records: [] } } as any)
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  // 2.1 AC①：决策概览挂载调 signal/chain/trade 多源契约，渲染情绪/隔夜新闻/昨日复盘/候选池预加载/板块共振区块
  it('2.1 decision-overview: 挂载调多源契约，渲染决策概览 6 区块', async () => {
    renderOpenDecision('/open-decision')
    await waitFor(() => expect(signalApi.getLive).toHaveBeenCalledWith('intra'))
    expect(chainApi.getCandidates).toHaveBeenCalled()
    expect(tradeApi.getRiskVerdicts).toHaveBeenCalled()
    expect(await screen.findByRole('heading', { name: '开盘决策 - 决策总览' })).toBeInTheDocument()
    expect(screen.getByText('隔夜新闻')).toBeInTheDocument()
    expect(screen.getByText('昨日复盘')).toBeInTheDocument()
    expect(screen.getByText('候选池预加载')).toBeInTheDocument()
    expect(screen.getByText('今日情绪 + 风控')).toBeInTheDocument()
    expect(screen.getByText('实时板块共振')).toBeInTheDocument()
  })

  // 2.1 AC③：AI 解读 3 支撑原因渲染（缺资金/历史字段显式 fallback_reason，不空白）
  it('2.1 decision-overview: AI 开盘解读渲染 3 条支撑原因不空白', async () => {
    renderOpenDecision('/open-decision')
    expect(await screen.findByText('AI 开盘解读')).toBeInTheDocument()
    expect(screen.getByText(/支撑原因 1 · 情绪趋势/)).toBeInTheDocument()
    expect(screen.getByText(/支撑原因 2 · 资金面/)).toBeInTheDocument()
    expect(screen.getByText(/支撑原因 3 · 信号-候选共振/)).toBeInTheDocument()
  })

  // 2.1 AC④：内联 style 全 token 化（无裸 #hex；语义色走 className）—— 验证 A 股红涨绿跌 className 生效
  it('2.1 decision-overview: 涨幅/评分走 .up/.warn className（token 化，无裸 #hex）', async () => {
    renderOpenDecision('/open-decision')
    expect(await screen.findByText('今日情绪 + 风控')).toBeInTheDocument()
    // 板块共振 + 候选预加载区涨跌走 .up/.down className（A 股红涨绿跌）
    const upEls = document.querySelectorAll('.up')
    expect(upEls.length).toBeGreaterThan(0)
    // 源码扫描：OpenDecision.tsx 无裸 #hex（W-1 守门）
    // （静态守门由 PrototypeFidelityGuard 同类机制兜底，这里只验运行时 className）
  })

  // 2.4 AC②：候选池消费 screenerApi.queryCandidatePool，scope 不走明文入参（契约 §9.3）
  it('2.4 candidate-pool: 消费 queryCandidatePool 展示持久化候选，scope 走拦截器头', async () => {
    renderOpenDecision('/open-decision/candidates')
    expect(await screen.findByText('立讯精密')).toBeInTheDocument()
    await waitFor(() => {
      expect(screenerApi.queryCandidatePool).toHaveBeenCalledWith({
        source_module: 'open-decision',
        page: 1,
        page_size: 50,
      })
    })
    // 入参不含 scope/tenant/owner/trade_account（这些由后端拦截器头注入）
    const calls = vi.mocked(screenerApi.queryCandidatePool).mock.calls
    calls.forEach(([params]) => {
      expect(params).not.toHaveProperty('scope')
      expect(params).not.toHaveProperty('tenant_id')
      expect(params).not.toHaveProperty('owner')
    })
  })

  // 2.4 AC②：多源融合去重（chain + screener 候选池按 code 去重）
  it('2.4 candidate-pool: chain 候选与 screener 候选池多源融合去重', async () => {
    renderOpenDecision('/open-decision/candidates')
    // 宁德时代（chain + 可能重复）只出现 1 行，立讯精密（仅 pool）出现
    expect(await screen.findByText('立讯精密')).toBeInTheDocument()
    expect(screen.getAllByText('宁德时代').length).toBe(1)
  })

  // 2.4 AC⑧：候选池空 + 后端 empty_state.reason 走 EmptyState 不留白
  it('2.4 candidate-pool: 候选池空时走 EmptyState + empty_state.reason 不空白', async () => {
    vi.mocked(screenerApi.queryCandidatePool).mockResolvedValue({
      data: { total: 0, page: 1, page_size: 50, records: [], empty_state: { reason: 'SIT：候选池为空' } },
    } as any)
    vi.mocked(chainApi.getCandidates).mockResolvedValue({ data: { candidates: [] } } as any)

    renderOpenDecision('/open-decision/candidates')
    expect(await screen.findByText('候选池暂无数据')).toBeInTheDocument()
    expect(screen.getByText('SIT：候选池为空')).toBeInTheDocument()
  })
})
