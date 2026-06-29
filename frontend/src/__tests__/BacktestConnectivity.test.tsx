import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Backtest from '../pages/Backtest'
import { backtestApi, tradeApi } from '../api/client'

vi.mock('../api/client', () => ({
  backtestApi: {
    getFactors: vi.fn(),
    run: vi.fn(),
    compare: vi.fn(),
  },
  tradeApi: {
    getOrders: vi.fn(),
    getRiskVerdicts: vi.fn(),
    getDecisionContexts: vi.fn(),
  },
}))

function result(strategy_id: string, strategy_name: string, total_return: number) {
  return {
    strategy_id,
    strategy_name,
    total_return,
    annual_return: total_return,
    sharpe_ratio: 1.2,
    max_drawdown: -3.5,
    win_rate: 62.5,
    profit_factor: 1.4,
    avg_holding_days: 4,
    total_trades: 18,
    win_trades: 11,
    loss_trades: 7,
    start_date: '2026-05-01',
    end_date: '2026-06-29',
  }
}

function renderBacktest(route = '/backtest') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Backtest />
    </MemoryRouter>,
  )
}

describe('Backtest connectivity', () => {
  beforeEach(() => {
    vi.mocked(backtestApi.getFactors).mockResolvedValue({ data: { factors: [{ name: 'momentum' }, { name: 'quality' }] } } as any)
    vi.mocked(backtestApi.run).mockResolvedValue({
      data: {
        results: [result('strategy-live-1', '真实回测策略', 9.3)],
        windows: 3,
        elapsed: 1.2,
      },
    } as any)
    vi.mocked(backtestApi.compare).mockResolvedValue({
      data: {
        comparison: [result('strategy-live-2', '真实对比策略', 6.1)],
        winner: 'strategy-live-2',
      },
    } as any)
    vi.mocked(tradeApi.getOrders).mockResolvedValue({ data: { orders: [] } } as any)
    vi.mocked(tradeApi.getRiskVerdicts).mockResolvedValue({ data: { records: [] } } as any)
    vi.mocked(tradeApi.getDecisionContexts).mockResolvedValue({ data: { records: [] } } as any)
  })

  it('starts with real empty state instead of fixed backtest metrics', async () => {
    renderBacktest('/backtest')

    await waitFor(() => expect(backtestApi.getFactors).toHaveBeenCalled())
    expect(screen.getByText('暂无回测结果')).toBeInTheDocument()
    expect(screen.queryByText('23')).not.toBeInTheDocument()
    expect(screen.queryByText('+8.5%')).not.toBeInTheDocument()
    expect(screen.queryByText('-4.2%')).not.toBeInTheDocument()
  })

  it('runs backtest through backtest service and renders returned result', async () => {
    renderBacktest('/backtest/run')

    fireEvent.click(screen.getByRole('button', { name: '运行回测' }))

    await waitFor(() => expect(backtestApi.run).toHaveBeenCalledWith({ mode: 'all', windows: 3, top_n: 30, forward_days: 60 }))
    expect(await screen.findByText('真实回测策略')).toBeInTheDocument()
    expect(screen.getAllByText('+9.3%').length).toBeGreaterThan(0)
  })

  it('loads strategy comparison from backtest compare API instead of static rows', async () => {
    renderBacktest('/backtest/compare')

    await waitFor(() => expect(backtestApi.compare).toHaveBeenCalled())
    expect(await screen.findByText('真实对比策略')).toBeInTheDocument()
    expect(screen.queryByText('半导体竞价共振')).not.toBeInTheDocument()
    expect(screen.queryByText('价值回撤低吸')).not.toBeInTheDocument()
  })

  it('renders UAT compare response shape with strategies field', async () => {
    vi.mocked(backtestApi.compare).mockResolvedValue({
      data: {
        status: 'ok',
        strategies: [
          { strategy: 'momentum', avg_return: 0.07, samples: 617675, period: '2025-12-31 ~ 2026-06-29' },
        ],
      },
    } as any)

    renderBacktest('/backtest/compare')

    expect(await screen.findByText('momentum')).toBeInTheDocument()
    expect(screen.getByText('2025-12-31 ~ 2026-06-29')).toBeInTheDocument()
  })
})
