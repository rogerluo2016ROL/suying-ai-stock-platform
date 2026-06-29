import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { P0WorkflowNav } from '../components/layout'

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location">{location.pathname}</div>
}

function renderWorkflow(initialRoute = '/screener') {
  return render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <P0WorkflowNav currentStep="candidate" />
      <Routes>
        <Route path="*" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('P0WorkflowNav', () => {
  it('renders the P0 chain as tabs and navigates to each module route', () => {
    renderWorkflow()

    const nav = screen.getByLabelText('P0 主链路')
    expect(within(nav).getByRole('button', { name: /候选池/ })).toHaveAttribute('aria-current', 'step')
    expect(within(nav).getByRole('button', { name: /方案管理/ })).toBeInTheDocument()
    expect(within(nav).getByRole('button', { name: /下单面板/ })).toBeInTheDocument()
    expect(within(nav).getByRole('button', { name: /风控闸门/ })).toBeInTheDocument()
    expect(within(nav).getByRole('button', { name: /回测复盘/ })).toBeInTheDocument()

    fireEvent.click(within(nav).getByRole('button', { name: /方案管理/ }))
    expect(screen.getByTestId('location')).toHaveTextContent('/strategy')

    fireEvent.click(within(nav).getByRole('button', { name: /风控闸门/ }))
    expect(screen.getByTestId('location')).toHaveTextContent('/trade/risk-verdicts')
  })
})
