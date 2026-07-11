import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Signals from '../../src/pages/Signals'
import { signalApi, tradeApi } from '../../src/api/client'

// SIT scope：Signals 6.0/6.1/6.2/6.3 四 preview 的 sub-tab 渲染 + API 调用契约。
// API client 走 vi.mock（项目既有 Signals.test.tsx 同款），断言"触发→以正确参数调了正确 API"。

vi.mock('../../src/api/client', () => ({
  signalApi: {
    getLive: vi.fn(),
    getHistory: vi.fn(),
    analyzeCode: vi.fn(),
    getDataStatus: vi.fn(),
  },
  tradeApi: {
    getRiskVerdicts: vi.fn(),
  },
}))

const LIVE = [
  { code: '300750', name: '宁德时代', signal: '买入', strength: 82, reason: '竞价强 + 资金共振', risk: '低' },
  { code: '688981', name: '中芯国际', signal: '强买', strength: 78, reason: '半导体共振', risk: '中' },
]

const HISTORY = [
  { code: '300750', name: '宁德时代', signal: '买入', date: '2026-06-25', hit: true, return_pct: 8.2, strength: 82 },
  { code: '300750', name: '宁德时代', signal: '强买', date: '2026-06-24', hit: false, return_pct: -1.3, strength: 85 },
]

const RISK_VERDICT = {
  records: [
    {
      details: {
        risk_check: {
          checks: [
            { rule: 'audit', level: 'pass', message: '标准无保留 · 安永华明 · 2025年报' },
            { rule: 'announce', level: 'warn', message: '减持 0.5%, 股东大会, 业绩说明会' },
            { rule: 'st_delist', level: 'pass', message: '正常上市, 创业板' },
            { rule: 'finance', level: 'pass', message: '营收预增, 净利润预增' },
          ],
        },
      },
    },
  ],
}

function renderSignals(route = '/signals') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Signals />
    </MemoryRouter>,
  )
}

describe('Signals 四 preview SIT (6.0/6.1/6.2/6.3)', () => {
  beforeEach(() => {
    vi.mocked(signalApi.getLive).mockResolvedValue({ data: { signals: LIVE } } as any)
    vi.mocked(signalApi.getHistory).mockResolvedValue({ data: { history: HISTORY } } as any)
    vi.mocked(signalApi.analyzeCode).mockResolvedValue({
      data: { code: '300750', risk_score: 28, verdict: 'warn', blockers: [] },
    } as any)
    vi.mocked(signalApi.getDataStatus).mockResolvedValue({
      data: {
        status: 'ok', refreshed_at: '2026-07-11T02:52:27Z', total_tables: 1,
        active_tables: 1, total_rows: 1, sync_map: {},
        sources: [{ key: 'daily_kline', name: '日K线行情', category: '行情', source: 'Tushare daily', update: '每日盘后', note: '', rows: 1, min_date: '2026-07-03', max_date: '2026-07-03', status: 'active' }],
      },
    } as any)
    vi.mocked(tradeApi.getRiskVerdicts).mockResolvedValue({ data: RISK_VERDICT } as any)
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  // AC① + AC②：6.0 signal-detail — 实时触发队列 + 选中的信号 verdict 头
  it('6.0 detail: 渲染触发队列与选中信号 verdict，缺数据走 EmptyState', async () => {
    renderSignals('/signals')
    expect(screen.getByRole('heading', { name: '交易信号 - 信号详情' })).toBeInTheDocument()
    expect(await screen.findByText('实时触发队列')).toBeInTheDocument()
    // verdict 头展示选中信号强度（pos 单元格）
    expect(screen.getByText('82', { selector: '.pos' })).toBeInTheDocument()
    // 列点击切换选中
    fireEvent.click(screen.getByText('中芯国际'))
    expect(screen.getByText('78', { selector: '.pos' })).toBeInTheDocument()
  })

  it('6.0 detail: getLive 返回空时不展示演示股票，走 EmptyState', async () => {
    vi.mocked(signalApi.getLive).mockResolvedValue({ data: { signals: [] } } as any)
    renderSignals('/signals')
    expect(await screen.findByText('暂无实时信号')).toBeInTheDocument()
    expect(screen.queryByText('宁德时代')).not.toBeInTheDocument()
  })

  // AC① + AC②：6.1 signal-overview — 强弱分布 dim-row
  it('6.1 overview: 渲染信号强弱分布与计数', async () => {
    renderSignals('/signals/overview')
    expect(screen.getByRole('heading', { name: '交易信号 - 信号总览' })).toBeInTheDocument()
    expect(await screen.findByText('信号强弱分布')).toBeInTheDocument()
    const overview = screen.getByText('信号强弱分布').closest('.prototype-card')!
    expect(within(overview).getByText('强买')).toBeInTheDocument()
  })

  // AC① + AC②：6.2 signal-history — 评分趋势图 + 命中率回看表
  it('6.2 history: 趋势图 + 命中回看表，调 getHistory 正确参数', async () => {
    renderSignals('/signals/history')
    expect(screen.getByRole('heading', { name: '交易信号 - 信号历史' })).toBeInTheDocument()
    expect(await screen.findByText('信号评分趋势')).toBeInTheDocument()
    expect(screen.getByText('命中率回看')).toBeInTheDocument()
    expect(signalApi.getHistory).toHaveBeenCalled()
    // 命中表渲染行（formatReturn 返回 +8.2%；KPI 历史均值也可能含此值，故断言至少一处）
    expect(screen.getAllByText((_, node) => !!node?.textContent && node.textContent.includes('+8.2%')).length).toBeGreaterThan(0)
  })

  it('6.2 history: getHistory 返回空时走 EmptyState', async () => {
    vi.mocked(signalApi.getHistory).mockResolvedValue({ data: { history: [] } } as any)
    renderSignals('/signals/history')
    expect(await screen.findByText('暂无历史信号')).toBeInTheDocument()
  })

  // AC① + AC② + AC③：6.3 risk-scan — op-hint + 4 项检查卡 + tradeApi.getRiskVerdicts
  it('6.3 risk: 调 analyzeCode + getRiskVerdicts，渲染 4 项检查卡', async () => {
    renderSignals('/signals/risk')
    expect(screen.getByRole('heading', { name: '交易信号 - 风险扫描' })).toBeInTheDocument()
    await waitFor(() => expect(signalApi.analyzeCode).toHaveBeenCalledWith('300750'))
    await waitFor(() => expect(tradeApi.getRiskVerdicts).toHaveBeenCalledWith({ code: '300750', page_size: 5 }))
    expect(screen.getByText('RiskVerdict 预检')).toBeInTheDocument()
    expect(screen.getByText('审计检查')).toBeInTheDocument()
    expect(screen.getByText('公告检查')).toBeInTheDocument()
    expect(screen.getByText('ST/退市检查')).toBeInTheDocument()
    expect(screen.getByText('业绩检查')).toBeInTheDocument()
    // 公告检查是 warn 态，展示"关注"徽标
    expect(screen.getByText('关注')).toBeInTheDocument()
  })

  it('6.3 risk: 无实时信号时不触发风险扫描', async () => {
    vi.mocked(signalApi.getLive).mockResolvedValue({ data: { signals: [] } } as any)
    renderSignals('/signals/risk')
    expect(await screen.findByText('暂无可扫描信号')).toBeInTheDocument()
    expect(signalApi.analyzeCode).not.toHaveBeenCalled()
    expect(tradeApi.getRiskVerdicts).not.toHaveBeenCalled()
  })

  // AC②：sub-tab 切换（activeKey 由 pathname 决定）
  it('sub-tab 切换：detail → history → risk 各渲染专属内容', async () => {
    renderSignals('/signals')
    await screen.findByText('实时触发队列')

    fireEvent.click(screen.getByRole('tab', { name: /信号总览/ }))
    expect(await screen.findByText('信号强弱分布')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: /信号历史/ }))
    expect(await screen.findByText('信号评分趋势')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: /风险扫描/ }))
    await waitFor(() => expect(screen.getByText('审计检查')).toBeInTheDocument())
  })
})
