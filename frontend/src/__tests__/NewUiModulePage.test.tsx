import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Screener from '../pages/Screener'
import Trade from '../pages/Trade'
import Strategy, { buildTradeUrlForPick } from '../pages/Strategy'

function renderPage(page: React.ReactNode, route: string) {
  return render(<MemoryRouter initialEntries={[route]}>{page}</MemoryRouter>)
}

describe('new UI module rollout', () => {
  it('renders screener directly in the prototype UI', () => {
    renderPage(<Screener />, '/screener/models')

    expect(screen.getByLabelText('智能选股页签')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /模型对比/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.queryByLabelText('P0 主链路')).not.toBeInTheDocument()
    expect(screen.getByText('模型评分差异')).toBeInTheDocument()
    expect(screen.getByText('候选池排行')).toBeInTheDocument()
  })

  it('renders trade center as new UI and keeps live trading locked by default', () => {
    renderPage(<Trade />, '/trade/order')

    expect(screen.getByRole('heading', { name: '交易中心 - 下单面板' })).toBeInTheDocument()
    expect(screen.getByText('模拟盘安全')).toBeInTheDocument()
    expect(screen.getByText('实盘锁定')).toBeInTheDocument()
  })

  it('preserves strategy-to-trade lineage URL builder while using new UI', () => {
    renderPage(<Strategy />, '/strategy')

    expect(screen.getByRole('heading', { name: '方案管理 - 方案列表' })).toBeInTheDocument()
    expect(buildTradeUrlForPick('PLAN-1', { code: '300750', entry_price: 218.5 })).toContain('decision_context_id=CTX-PLAN-1-manual-300750')
  })
})
