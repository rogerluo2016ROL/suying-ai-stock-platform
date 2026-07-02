import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import OpenDecision from '../pages/OpenDecision'
import { chainApi, screenerApi, signalApi, tradeApi } from '../api/client'

vi.mock('../api/client', () => ({
  signalApi: {
    getDashboardAuction: vi.fn(),
    getLive: vi.fn(),
  },
  chainApi: {
    getCandidates: vi.fn(),
  },
  screenerApi: {
    queryCandidatePool: vi.fn(),
    addWatchlist: vi.fn(),
    listWatchlist: vi.fn(),
  },
  tradeApi: {
    getAccount: vi.fn(),
    getPositions: vi.fn(),
    getOrders: vi.fn(),
    getRiskVerdicts: vi.fn(),
    getDecisionContexts: vi.fn(),
  },
}))

function renderOpenDecision(route = '/open-decision') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <OpenDecision />
    </MemoryRouter>,
  )
}

function expectPrototypeText(label: string) {
  expect(screen.getAllByText(label, { exact: false }).length).toBeGreaterThan(0)
}

describe('OpenDecision prototype pages', () => {
  beforeEach(() => {
    vi.mocked(signalApi.getDashboardAuction).mockResolvedValue({ data: { total_count: 328 } } as any)
    vi.mocked(signalApi.getLive).mockResolvedValue({
      data: {
        session: 'intra',
        signals: [
          {
            code: '300750',
            name: '宁德时代',
            level: 'strong_buy',
            score: 85,
            confidence: 82,
            dimensions: { technical: 86, fundamental: 80, money_flow: 78, sentiment: 88 },
          },
          {
            code: '000858',
            name: '五粮液',
            level: 'sell',
            score: 32,
            confidence: 45,
            dimensions: { technical: 35, fundamental: 62, money_flow: 28, sentiment: 30 },
          },
        ],
      },
    } as any)
    vi.mocked(chainApi.getCandidates).mockResolvedValue({
      data: {
        filter: 'all',
        total_count: 2,
        candidates: [
          { code: '300750', name: '宁德时代', industry: '新能源', score: 90, resonance_level: '强启动', last_change_pct: 8.2 },
          { code: '688981', name: '中芯国际', industry: '半导体', score: 88, resonance_level: '启动', last_change_pct: 5.8 },
        ],
        filter_summary: {},
        resonance_summary: {},
        elapsed_ms: 12,
      },
    } as any)
    vi.mocked(tradeApi.getAccount).mockResolvedValue({
      data: { account: { total_capital: 1280000, total_assets: 1280000, market_value: 894000, available: 386000, total_pnl: 23500 } },
    } as any)
    vi.mocked(tradeApi.getPositions).mockResolvedValue({
      data: {
        positions: [{ code: '300750', name: '宁德时代', volume: 600, avg_cost: 210, current_price: 218.5, market_value: 131100, pnl: 5100, pnl_pct: 0.082 }],
        total_market_value: 131100,
        total_pnl: 5100,
      },
    } as any)
    vi.mocked(tradeApi.getOrders).mockResolvedValue({
      data: {
        orders: [{ id: 'ORD-1', code: '300750', name: '宁德时代', direction: 'buy', price: 218.5, volume: 600, status: 'filled', created_at: '2026-06-29T09:32:18Z' }],
        total: 1,
      },
    } as any)
    vi.mocked(tradeApi.getRiskVerdicts).mockResolvedValue({
      data: {
        total: 2,
        page: 1,
        page_size: 20,
        records: [
          { id: 1, verdict_id: 'RV-1', tenant_id: 't1', result: 'pass', scope: 'candidate', trade_mode: 'paper', symbol: '300750', details: {}, created_at: '2026-06-29T09:20:00Z' },
          { id: 2, verdict_id: 'RV-2', tenant_id: 't1', result: 'reject', scope: 'candidate', trade_mode: 'paper', symbol: '000858', details: {}, created_at: '2026-06-29T09:21:00Z' },
        ],
      },
    } as any)
    vi.mocked(tradeApi.getDecisionContexts).mockResolvedValue({
      data: {
        total: 1,
        page: 1,
        page_size: 20,
        records: [{ id: 1, decision_context_id: 'DC-1', tenant_id: 't1', source_type: 'strategy', symbol: '300750', plan_id: 'PLAN-OPEN-0925', intent: '开盘强势策略', payload: {}, created_at: '2026-06-29T09:25:00Z' }],
      },
    } as any)
    vi.mocked(screenerApi.queryCandidatePool).mockResolvedValue({
      data: {
        total: 0,
        page: 1,
        page_size: 50,
        records: [],
        empty_state: { reason: '候选池为空，等待选股/竞价/信号写入。' },
      },
    } as any)
  })

  it.each([
    [
      '/open-decision',
      ['当前时间', '隔夜新闻', '昨日复盘', '候选池预加载', '实时板块共振'],
    ],
    [
      '/open-decision/auction',
      ['竞价分析引擎', '竞价意图全景', '抢筹 TOP 10', '出货预警 TOP 10', '竞价选股引擎', '可转债竞价', '全量竞价明细', '候选池预览'],
    ],
    [
      '/open-decision/signals',
      ['验证工作台 · 逐条确认信号 · Kronos 交叉验证 · 一键推送候选池', '批量确认买入信号', 'Kronos 30日预测', '风险检查', '一键推送已确认'],
    ],
    [
      '/open-decision/candidates',
      ['P0 主链路', '多源候选池', '风控排查', '交易方案预览', '风控预检'],
    ],
    [
      '/open-decision/execution',
      ['总资产', '今日订单', '持仓', '自动交易策略', '今日方案', '需关注'],
    ],
  ])('renders prototype-critical content for %s', (route, labels) => {
    renderOpenDecision(route)

    labels.forEach(label => {
      expectPrototypeText(label)
    })
  })

  it('renders auction analysis with actual candidate and sector panels', () => {
    renderOpenDecision('/open-decision/auction')

    expect(screen.getByRole('heading', { name: '开盘决策 - 竞价分析' })).toBeInTheDocument()
    expect(screen.getByText('抢筹 TOP 10')).toBeInTheDocument()
    expect(screen.getByText('板块共振详情')).toBeInTheDocument()
    expect(screen.getByText('已锁定板块')).toBeInTheDocument()
    return screen.findAllByText('宁德时代').then(items => {
      expect(items.length).toBeGreaterThan(0)
    })
  })

  it('matches the auction prototype workbench hierarchy', () => {
    renderOpenDecision('/open-decision/auction')

    expect(screen.getByText('竞价风险提示 · 高开过热板块需二次确认')).toBeInTheDocument()
    expect(screen.getByText('最近刷新来自 dashboard/auction 与 signal/live')).toBeInTheDocument()
    expect(screen.getByText('中性观察')).toBeInTheDocument()
    expect(screen.getByText('四维评分')).toBeInTheDocument()
    expect(screen.getByText('工作流引导')).toBeInTheDocument()
    expect(screen.getByText('锁定强势板块 -> 切换到竞价选股引擎')).toBeInTheDocument()
  })

  it('matches the signal scan verification workbench prototype', () => {
    renderOpenDecision('/open-decision/signals')

    expect(screen.getByText('锁定板块:')).toBeInTheDocument()
    expect(screen.getByText('仅自选')).toBeInTheDocument()
    expect(screen.getByText('排序:')).toBeInTheDocument()
    expect(screen.getByText('逐条确认决策')).toBeInTheDocument()
    expect(screen.getByText('选中股票')).toBeInTheDocument()
    expect(screen.getByText('六维评分')).toBeInTheDocument()
    expect(screen.getByText('决策分类')).toBeInTheDocument()
    expect(screen.getByText('一键推送已确认 -> 候选池')).toBeInTheDocument()
  })

  it('does not render static overnight news without a live news feed', () => {
    renderOpenDecision('/open-decision')

    expect(screen.queryByText('中芯国际: 收到证监会立案调查通知书')).not.toBeInTheDocument()
    expect(screen.queryByText('外盘')).not.toBeInTheDocument()
    expect(screen.getByText('暂无隔夜新闻实时接口；不展示演示新闻。')).toBeInTheDocument()
    expect(screen.getByText('等待新闻/舆情接口返回后生成摘要')).toBeInTheDocument()
  })

  it('switches to candidate pool without falling back to a placeholder', () => {
    renderOpenDecision('/open-decision')

    fireEvent.click(screen.getByRole('tab', { name: /候选池/ }))
    expect(screen.getByRole('heading', { name: '开盘决策 - 候选池' })).toBeInTheDocument()
    expectPrototypeText('Candidate 对象预览')
  })

  it('loads open decision data from signal, chain and trade APIs', async () => {
    renderOpenDecision('/open-decision/execution')

    expect(await screen.findByText('1单 · 成交1 · 待成交0')).toBeInTheDocument()
    await waitFor(() => {
      expect(signalApi.getDashboardAuction).toHaveBeenCalled()
      expect(signalApi.getLive).toHaveBeenCalledWith('intra')
      expect(chainApi.getCandidates).toHaveBeenCalledWith({ filter: 'all', top_n: 20 })
      expect(tradeApi.getAccount).toHaveBeenCalled()
      expect(tradeApi.getPositions).toHaveBeenCalled()
      expect(tradeApi.getOrders).toHaveBeenCalled()
      expect(tradeApi.getRiskVerdicts).toHaveBeenCalledWith({ page: 1, page_size: 20 })
      expect(tradeApi.getDecisionContexts).toHaveBeenCalledWith({ page: 1, page_size: 20 })
    })
  })

  it('uses dashboard auction date for the open decision freshness bar', async () => {
    vi.mocked(signalApi.getDashboardAuction).mockResolvedValue({
      data: { date: '2026-06-29', total: 1, picks: [] },
    } as any)

    renderOpenDecision('/open-decision/auction')

    expect(await screen.findByText('交易日：2026-06-29')).toBeInTheDocument()
  })

  it('uses dashboard auction picks before derived signal rows on the auction tab', async () => {
    vi.mocked(signalApi.getDashboardAuction).mockResolvedValue({
      data: {
        date: '2026-06-29',
        total: 1,
        picks: [
          {
            code: '600171',
            name: '上海贝岭',
            industry: '半导体',
            gap_pct: 1.67,
            score: 51.3,
            vol_z: 0.88,
          },
        ],
      },
    } as any)
    vi.mocked(signalApi.getLive).mockResolvedValue({ data: { session: 'intra', signals: [] } } as any)
    vi.mocked(chainApi.getCandidates).mockResolvedValue({ data: { candidates: [] } } as any)

    renderOpenDecision('/open-decision/auction')

    expect((await screen.findAllByText('上海贝岭')).length).toBeGreaterThan(0)
    expect(screen.queryByText('宁德时代')).not.toBeInTheDocument()
  })

  it('handles backend live signal shape without crashing', async () => {
    vi.mocked(signalApi.getDashboardAuction).mockResolvedValue({ data: { date: '2026-06-29', total: 0, picks: [] } } as any)
    vi.mocked(signalApi.getLive).mockResolvedValue({
      data: {
        session: 'intra',
        trade_date: '2026-06-26',
        signals: [
          {
            code: '002898',
            name: '赛隆退',
            price: 0.35,
            change_pct: -95.78,
            signal: 'Bearish',
            confidence: 72,
          },
        ],
      },
    } as any)
    vi.mocked(chainApi.getCandidates).mockResolvedValue({ data: { candidates: [] } } as any)

    renderOpenDecision('/open-decision/signals')

    expect((await screen.findAllByText('赛隆退')).length).toBeGreaterThan(0)
    expect(screen.getAllByText('减仓').length).toBeGreaterThan(0)
  })

  it('shows signal live trade date on the signal scan tab', async () => {
    vi.mocked(signalApi.getDashboardAuction).mockResolvedValue({ data: { date: '2026-06-29', total: 0, picks: [] } } as any)
    vi.mocked(signalApi.getLive).mockResolvedValue({
      data: {
        session: 'intra',
        trade_date: '2026-06-26',
        signals: [],
      },
    } as any)

    renderOpenDecision('/open-decision/signals')

    expect(await screen.findByText('交易日：2026-06-26')).toBeInTheDocument()
  })

  // AC② 候选池消费 screenerApi.queryCandidatePool（M0 API，scope 不走明文入参，契约 §9.3）
  it('renders the persisted candidate pool from screenerApi.queryCandidatePool on the candidates tab', async () => {
    vi.mocked(screenerApi.queryCandidatePool).mockResolvedValue({
      data: {
        total: 1,
        page: 1,
        page_size: 50,
        records: [
          {
            pool_id: 'POOL-open-decision-2026-06-29-am',
            source_module: 'open-decision',
            source_mode: 'leader_scalp',
            name: '盘前候选',
            candidates: [
              { code: '002475', name: '立讯精密', score: 84, grade: 'A', rank: 1 },
            ],
          },
        ],
      },
    } as any)
    vi.mocked(chainApi.getCandidates).mockResolvedValue({ data: { candidates: [] } } as any)

    renderOpenDecision('/open-decision/candidates')

    expect(await screen.findByText('立讯精密')).toBeInTheDocument()
    expect(screen.getByText(/open-decision\/leader_scalp/)).toBeInTheDocument()
    // scope 不走明文：queryCandidatePool 入参只含 source_module / 分页，不含 scope/tenant/owner
    await waitFor(() => {
      expect(screenerApi.queryCandidatePool).toHaveBeenCalledWith({
        source_module: 'open-decision',
        page: 1,
        page_size: 50,
      })
    })
  })

  // AC⑧ 缺数据不空白：候选池空 + 后端返 empty_state.reason，走 EmptyState 不留白
  it('shows an EmptyState with backend empty_state.reason when the candidate pool is empty', async () => {
    vi.mocked(screenerApi.queryCandidatePool).mockResolvedValue({
      data: {
        total: 0,
        page: 1,
        page_size: 50,
        records: [],
        empty_state: { reason: '今日盘前候选池尚未写入，等待选股与竞价。' },
      },
    } as any)
    vi.mocked(chainApi.getCandidates).mockResolvedValue({ data: { candidates: [] } } as any)

    renderOpenDecision('/open-decision/candidates')

    expect(await screen.findByText('候选池暂无数据')).toBeInTheDocument()
    expect(screen.getByText('今日盘前候选池尚未写入，等待选股与竞价。')).toBeInTheDocument()
  })

  // DEF-3: 后端实际返 empty_state {hint, suggestion}（types.ts 标 {reason}）；最小侵入兼容三者
  it('DEF-3: shows backend empty_state.hint/suggestion (not just reason) when pool empty', async () => {
    vi.mocked(screenerApi.queryCandidatePool).mockResolvedValue({
      data: {
        total: 0,
        page: 1,
        page_size: 50,
        records: [],
        empty_state: { hint: '今日无新候选', suggestion: '建议盘后跑 leader_scalp 后再来。' },
      },
    } as any)
    vi.mocked(chainApi.getCandidates).mockResolvedValue({ data: { candidates: [] } } as any)

    renderOpenDecision('/open-decision/candidates')

    expect(await screen.findByText('候选池暂无数据')).toBeInTheDocument()
    // hint 优先于 reason；suggestion 作为 fallback 兜底
    expect(screen.getByText('今日无新候选')).toBeInTheDocument()
  })

  // AC③ 决策概览 AI 解读 3 支撑原因（缺字段显式 fallback_reason，不空白）
  it('renders AI open-market interpretation with 3 supporting reasons on the overview tab', async () => {
    renderOpenDecision('/open-decision')

    expect(await screen.findByText('AI 开盘解读')).toBeInTheDocument()
    expect(screen.getByText(/支撑原因 1/)).toBeInTheDocument()
    expect(screen.getByText(/支撑原因 2/)).toBeInTheDocument()
    expect(screen.getByText(/支撑原因 3/)).toBeInTheDocument()
    // signal/live 返回了评分 → 趋势原因不含 fallback_reason；资金/共振仍可能 fallback，但 3 条结构齐全不空白
    expect(screen.getAllByText(/fallback_reason|趋势环境|资金面|信号-候选共振/).length).toBeGreaterThan(0)
  })
})
