import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { strategyApi } from '../api/client'
import Strategy from '../pages/Strategy'

vi.mock('../api/client', () => ({
  strategyApi: {
    getPlans: vi.fn(),
  },
}))

function renderStrategy(route = '/strategy') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Strategy />
    </MemoryRouter>,
  )
}

describe('Strategy connectivity', () => {
  beforeEach(() => {
    vi.mocked(strategyApi.getPlans).mockResolvedValue({
      data: {
        plans: [{
          id: 'PLAN-live-001',
          name: '实盘联通方案',
          status: 'confirmed',
          model_name: 'all',
          max_positions: 5,
          capital: 500000,
          expected_return: 6.8,
          risk_score: 42,
          created_at: '2026-06-29T09:30:00Z',
          updated_at: '2026-06-29T10:00:00Z',
          picks: [{
            code: '002138',
            name: '顺络电子',
            candidate_id: 'CAND-live-002138',
            source_mode: 'leader_auction',
            entry_price: 24.8,
            score: 88,
          }],
        }, {
          id: 'PLAN-live-002',
          name: '备用联通方案',
          status: 'draft',
          model_name: 'hard_tech',
          max_positions: 3,
          capital: 300000,
          risk_score: 12,
          created_at: '2026-06-29T11:00:00Z',
          picks: [],
        }],
        total: 2,
      },
    } as any)
  })

  it('loads plan rows from strategy service instead of static prototype data', async () => {
    renderStrategy()

    expect(await screen.findByText('实盘联通方案')).toBeInTheDocument()
    expect(screen.getAllByText('PLAN-live-001').length).toBeGreaterThan(0)
    await waitFor(() => expect(strategyApi.getPlans).toHaveBeenCalled())
  })

  it('selects strategy detail by plan_id instead of always using the first plan', async () => {
    renderStrategy('/strategy/detail?plan_id=PLAN-live-002')

    expect(await screen.findByText('备用联通方案')).toBeInTheDocument()
    expect(screen.getByText(/模型 hard_tech/)).toBeInTheDocument()
  })

  it('does not show hard-coded drawdown or turnover in strategy comparison', async () => {
    renderStrategy('/strategy/compare')

    expect(await screen.findByText('实盘联通方案')).toBeInTheDocument()
    expect(screen.queryByText('-4.2%')).not.toBeInTheDocument()
    expect(screen.queryByText('38%')).not.toBeInTheDocument()
    expect(screen.getByText('仅展示策略服务字段')).toBeInTheDocument()
  })

  it('uses plan timestamps in reports instead of a fake realtime label', async () => {
    renderStrategy('/strategy/reports')

    expect(await screen.findByText('2026-06-29T10:00:00Z')).toBeInTheDocument()
    expect(screen.queryByText('服务实时')).not.toBeInTheDocument()
  })
})
