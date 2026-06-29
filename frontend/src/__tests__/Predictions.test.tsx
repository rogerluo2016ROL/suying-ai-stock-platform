import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Predictions from '../pages/Predictions'

vi.mock('echarts-for-react', () => ({
  default: ({ style }: { style?: React.CSSProperties }) => <div data-testid="mock-chart" style={style} />,
}))

vi.mock('../api/client', () => ({
  predictionApi: {
    predict: vi.fn().mockResolvedValue({
      data: {
        code: '300750',
        name: '宁德时代',
        current_price: 218.5,
        pred_last_close: 242.3,
        pred_return_pct: 12.5,
        confidence: 78,
        pred_trajectory: [],
      },
    }),
  },
}))

function renderPredictions(route = '/predictions') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Predictions />
    </MemoryRouter>,
  )
}

describe('Predictions prototype pages', () => {
  it('renders overview as portfolio/model summary, not the single-stock workspace', () => {
    renderPredictions('/predictions')

    expect(screen.getByRole('heading', { name: '预测总览' })).toBeInTheDocument()
    expect(screen.getByText('组合预测分布')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '单股预测' })).not.toBeInTheDocument()
  })

  it('renders single-stock workspace with non-empty chart area and right-side analysis', () => {
    renderPredictions('/predictions/single')

    expect(screen.getByRole('heading', { name: '单股预测' })).toBeInTheDocument()
    expect(screen.getByText(/宁德时代 预测路径/)).toBeInTheDocument()
    expect(screen.getByText('预测概览')).toBeInTheDocument()
    expect(screen.getByText('信号一致性')).toBeInTheDocument()
    expect(screen.getByText('因子贡献')).toBeInTheDocument()
    expect(screen.getAllByTestId('mock-chart').length).toBeGreaterThan(0)
  })

  it('switches tabs through the prototype tab bar', () => {
    renderPredictions('/predictions')

    fireEvent.click(screen.getByRole('tab', { name: /单股预测/ }))
    expect(screen.getByRole('heading', { name: '单股预测' })).toBeInTheDocument()
  })
})
