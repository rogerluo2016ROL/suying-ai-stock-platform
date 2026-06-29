import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Predictions from '../pages/Predictions'
import { predictionApi } from '../api/client'

vi.mock('echarts-for-react', () => ({
  default: ({ style }: { style?: React.CSSProperties }) => <div data-testid="mock-chart" style={style} />,
}))

vi.mock('../api/client', () => ({
  predictionApi: {
    getStatus: vi.fn(),
    getOverview: vi.fn(),
    predict: vi.fn(),
    predictFast: vi.fn(),
    compare: vi.fn(),
    getAccuracyBacktest: vi.fn(),
  },
}))

function renderPredictions(route = '/predictions') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Predictions />
    </MemoryRouter>,
  )
}

describe('Predictions', () => {
  beforeEach(() => {
    vi.mocked(predictionApi.getStatus).mockResolvedValue({
      data: {
        model_loaded: false,
        model: 'Kronos-mini',
        device: 'cpu',
        model_metadata: {
          loaded: false,
          checkpoint_status: 'not_loaded',
          inference_mode: 'status',
        },
      },
    } as any)
    vi.mocked((predictionApi as any).getOverview).mockResolvedValue({
      data: {
        model_metadata: {
          name: 'Kronos-mini',
          checkpoint_status: 'not_loaded',
          loaded: false,
        },
        fallback_reason: 'model checkpoint unavailable; using baseline predictor',
        sections: [
          { id: 'forecast-market', title: '预测市场', endpoint: '/api/v1/prediction/{code}' },
        ],
      },
    } as any)
    vi.mocked(predictionApi.predict).mockResolvedValue({
      data: {
        code: '300750',
        name: '宁德时代',
        current_price: 218.5,
        pred_last_close: 242.3,
        pred_return_pct: 12.5,
        adjusted_return_pct: 13.1,
        confidence: 78,
        trend: '上升',
        pred_low: 211.8,
        pred_high: 248.6,
        max_drawdown_pct: -4.2,
        pred_trajectory: [
          { day: 1, open: 218, high: 221, low: 216, close: 220 },
        ],
        model_metadata: {
          name: 'Kronos-mini',
          checkpoint_status: 'not_loaded',
          loaded: false,
        },
        data_freshness: {
          status: 'fresh',
          as_of: '2026-06-26',
          source: 'postgresql.daily_kline',
          quality_score: 96,
        },
        fallback_reason: 'model checkpoint unavailable; using baseline predictor',
      },
    } as any)
    vi.mocked((predictionApi as any).compare).mockResolvedValue({
      data: {
        mode: 'multi_compare',
        pred_days: 20,
        items: [{
          code: '300750',
          current_price: 218.5,
          pred_last_close: 242.3,
          pred_return_pct: 12.5,
          fallback_reason: 'model checkpoint unavailable; using baseline predictor',
        }],
      },
    } as any)
    vi.mocked((predictionApi as any).getAccuracyBacktest).mockResolvedValue({
      data: {
        mode: 'accuracy_backtest',
        fallback_reason: 'accuracy backtest awaits persisted prediction labels',
        metrics: [
          { window: '近30日', direction_accuracy: 0, sample_size: 0 },
        ],
      },
    } as any)
  })

  it('loads prediction service status on the overview page', async () => {
    renderPredictions('/predictions')

    expect(await screen.findByRole('heading', { name: '预测总览' })).toBeInTheDocument()
    expect(predictionApi.getStatus).toHaveBeenCalled()
    expect((predictionApi as any).getOverview).toHaveBeenCalled()
    expect(screen.getAllByText('Kronos-mini').length).toBeGreaterThan(0)
    expect(screen.getByText(/baseline predictor/)).toBeInTheDocument()
  })

  it('keeps single-stock prediction empty until a real prediction runs', async () => {
    renderPredictions('/predictions/single')

    expect(screen.getByRole('heading', { name: '单股预测' })).toBeInTheDocument()
    expect(await screen.findByText('暂无预测结果')).toBeInTheDocument()
    expect(screen.queryByText(/宁德时代 预测路径/)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '开始预测' }))

    await waitFor(() => {
      expect(predictionApi.predict).toHaveBeenCalledWith('300750', 30)
    })
    expect(await screen.findByText('宁德时代 预测路径')).toBeInTheDocument()
    expect(screen.getByText('2026-06-26')).toBeInTheDocument()
    expect(screen.getByText(/baseline predictor/)).toBeInTheDocument()
  })

  it('runs multi-stock compare through the prediction service', async () => {
    renderPredictions('/predictions/compare')

    fireEvent.click(await screen.findByRole('button', { name: '运行对比' }))

    await waitFor(() => {
      expect((predictionApi as any).compare).toHaveBeenCalledWith(['300750', '000001', '002594'], 20)
    })
    expect(await screen.findByText('300750')).toBeInTheDocument()
    expect(screen.getByText('+12.5%')).toBeInTheDocument()
  })

  it('falls back to fast single-code predictions when compare endpoint is unavailable', async () => {
    vi.mocked((predictionApi as any).compare).mockRejectedValue({ response: { status: 404 } })
    vi.mocked(predictionApi.predictFast).mockImplementation((fastCode: string) => Promise.resolve({
      data: {
        code: fastCode,
        current_price: 218.5,
        pred_last_close: 242.3,
        pred_return_pct: 12.5,
        fallback_reason: 'compare endpoint unavailable; using fast prediction fallback',
      },
    } as any))

    renderPredictions('/predictions/compare')

    fireEvent.click(await screen.findByRole('button', { name: '运行对比' }))

    await waitFor(() => {
      expect(predictionApi.predictFast).toHaveBeenCalledWith('300750', 20)
    })
    expect(await screen.findByText('300750')).toBeInTheDocument()
    expect(screen.getAllByText('+12.5%').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/fast prediction fallback/).length).toBeGreaterThan(0)
  })

  it('loads prediction accuracy backtest instead of fixed metrics', async () => {
    renderPredictions('/predictions/backtest')

    expect(await screen.findByText('近30日')).toBeInTheDocument()
    expect((predictionApi as any).getAccuracyBacktest).toHaveBeenCalled()
    expect(screen.getByText(/awaits persisted prediction labels/)).toBeInTheDocument()
  })
})
