import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import P0Workflow from '../pages/P0Workflow'
import RiskControl from '../pages/RiskControl'

function renderPage(page: React.ReactNode, route: string) {
  return render(<MemoryRouter initialEntries={[route]}>{page}</MemoryRouter>)
}

describe('Phase 4 workflow pages', () => {
  it('renders the P0 decision chain with the five shared objects', () => {
    renderPage(<P0Workflow />, '/p0')

    expect(screen.getByRole('heading', { name: 'P0 主链路' })).toBeInTheDocument()
    expect(screen.getByText('Candidate')).toBeInTheDocument()
    expect(screen.getByText('Plan')).toBeInTheDocument()
    expect(screen.getByText('Order')).toBeInTheDocument()
    expect(screen.getByText('RiskVerdict')).toBeInTheDocument()
    expect(screen.getByText('BacktestReview')).toBeInTheDocument()
  })

  it('renders risk audit as a concrete RiskVerdict view instead of a generic note', () => {
    renderPage(<RiskControl />, '/risk/audit')

    expect(screen.getByRole('heading', { name: '风控中心 - 事件审计' })).toBeInTheDocument()
    expect(screen.getByText('RiskVerdict 审计')).toBeInTheDocument()
    expect(screen.getByText('DecisionContext')).toBeInTheDocument()
    expect(screen.queryByText(/风控总览、持仓风险、策略回撤/)).not.toBeInTheDocument()
  })
})
