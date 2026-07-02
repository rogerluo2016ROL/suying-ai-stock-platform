import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Signals from '../pages/Signals'
import { signalApi, tradeApi } from '../api/client'

vi.mock('../api/client', () => ({
  signalApi: {
    getLive: vi.fn(),
    getHistory: vi.fn(),
    analyzeCode: vi.fn(),
  },
  tradeApi: {
    getRiskVerdicts: vi.fn(),
  },
}))

function renderSignals(route = '/signals') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Signals />
    </MemoryRouter>,
  )
}

describe('Signals prototype pages', () => {
  beforeEach(() => {
    vi.mocked(signalApi.getLive).mockResolvedValue({
      data: {
        signals: [
          { code: '300750', name: '宁德时代', signal: '买入', strength: 82, reason: '竞价强 + 资金共振', risk: '低' },
          { code: '688981', name: '中芯国际', signal: '强买', strength: 78, reason: '半导体共振', risk: '中' },
        ],
      },
    } as any)
    vi.mocked(signalApi.getHistory).mockResolvedValue({
      data: {
        history: [
          { code: '300750', name: '宁德时代', signal: '买入', date: '2026-06-25', hit: true, return_pct: 8.2 },
        ],
      },
    } as any)
    vi.mocked(signalApi.analyzeCode).mockResolvedValue({
      data: { code: '300750', risk_score: 28, verdict: 'warn', blockers: [] },
    } as any)
    vi.mocked(tradeApi.getRiskVerdicts).mockResolvedValue({
      data: {
        records: [
          {
            details: {
              risk_check: {
                checks: [
                  { rule: 'audit', level: 'pass', message: '标准无保留 · 安永华明' },
                  { rule: 'announce', level: 'warn', message: '减持 0.5%, 股东大会' },
                  { rule: 'st_delist', level: 'pass', message: '正常上市, 创业板' },
                  { rule: 'finance', level: 'pass', message: '营收预增, 净利润预增' },
                ],
              },
            },
          },
        ],
      },
    } as any)
  })

  it('renders live signal detail without placeholder skeleton copy', async () => {
    renderSignals('/signals')

    expect(screen.getByRole('heading', { name: '交易信号 - 信号详情' })).toBeInTheDocument()
    expect(await screen.findByText('实时触发队列')).toBeInTheDocument()
    expect(await screen.findByText('宁德时代')).toBeInTheDocument()
    expect(screen.getByText('买入')).toBeInTheDocument()
    expect(screen.queryByText('信号页面骨架')).not.toBeInTheDocument()
  })

  it('does not fall back to hard-coded live signals when the API returns empty data', async () => {
    vi.mocked(signalApi.getLive).mockResolvedValue({ data: { signals: [] } } as any)

    renderSignals('/signals')

    expect(await screen.findByText('暂无实时信号')).toBeInTheDocument()
    expect(screen.queryByText('宁德时代')).not.toBeInTheDocument()
    expect(screen.queryByText('中芯国际')).not.toBeInTheDocument()
  })

  it('does not fall back to hard-coded history when the history API returns empty data', async () => {
    vi.mocked(signalApi.getHistory).mockResolvedValue({ data: { history: [] } } as any)

    renderSignals('/signals/history')

    expect(await screen.findByText('暂无历史信号')).toBeInTheDocument()
    expect(screen.queryByText('比亚迪')).not.toBeInTheDocument()
  })

  it('does not run risk scan without a real live signal', async () => {
    vi.mocked(signalApi.getLive).mockResolvedValue({ data: { signals: [] } } as any)

    renderSignals('/signals/risk')

    expect(await screen.findByText('暂无可扫描信号')).toBeInTheDocument()
    expect(signalApi.analyzeCode).not.toHaveBeenCalled()
  })

  it('switches to history and risk scan views with prototype content', async () => {
    renderSignals('/signals')

    fireEvent.click(screen.getByRole('tab', { name: /信号历史/ }))
    expect(screen.getByRole('heading', { name: '交易信号 - 信号历史' })).toBeInTheDocument()
    expect(await screen.findByText('信号评分趋势')).toBeInTheDocument()
    expect(screen.getByText('命中率回看')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: /风险扫描/ }))
    expect(screen.getByRole('heading', { name: '交易信号 - 风险扫描' })).toBeInTheDocument()
    await waitFor(() => expect(signalApi.analyzeCode).toHaveBeenCalledWith('300750'))
    expect(screen.getByText('RiskVerdict 预检')).toBeInTheDocument()
    await waitFor(() => expect(tradeApi.getRiskVerdicts).toHaveBeenCalledWith({ code: '300750', page_size: 5 }))
    expect(screen.getByText('审计检查')).toBeInTheDocument()
    expect(screen.getByText('公告检查')).toBeInTheDocument()
  })
})
