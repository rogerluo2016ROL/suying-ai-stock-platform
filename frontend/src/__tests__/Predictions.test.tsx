import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Predictions from '../pages/Predictions'
import { predictionApi, screenerApi } from '../api/client'

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
  screenerApi: {
    queryCandidatePool: vi.fn(),
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
    // 5.0 概览候选池预测排行：默认返回空候选池（走 EmptyState）
    vi.mocked(screenerApi.queryCandidatePool).mockResolvedValue({
      data: { total: 0, page: 1, page_size: 20, records: [], empty_state: { reason: '候选池暂无记录' } },
    } as any)
  })

  it('loads prediction service status on the overview page', async () => {
    renderPredictions('/predictions')

    expect(await screen.findByRole('heading', { name: 'K线预测总览' })).toBeInTheDocument()
    expect(predictionApi.getStatus).toHaveBeenCalled()
    expect((predictionApi as any).getOverview).toHaveBeenCalled()
    expect(screen.getAllByText('Kronos-mini').length).toBeGreaterThan(0)
    expect(screen.getByText(/baseline predictor/)).toBeInTheDocument()
  })

  // 5.0 prediction-overview：候选池预测排行消费 screenerApi.queryCandidatePool，
  // 渲染候选标的 + 预警摘要；后端命中率/预测价字段未齐走 fallback（不展示假数）。
  it('renders candidate-pool ranking + alert summary from queryCandidatePool on overview', async () => {
    vi.mocked(screenerApi.queryCandidatePool).mockResolvedValue({
      data: {
        total: 2,
        page: 1,
        page_size: 20,
        records: [{
          pool_id: 'POOL-leader_scalp-2026-06-26',
          source_module: 'screener',
          source_mode: 'leader_scalp',
          name: '选股-leader_scalp-2026-06-26',
          candidates: [
            { code: '300750', name: '宁德时代', score: 86, grade: 'S', rank: 1 },
            { code: '002594', name: '比亚迪', score: 61, grade: 'C', rank: 2 },
          ],
        }],
      },
    } as any)

    renderPredictions('/predictions')

    expect(await screen.findByRole('heading', { name: 'K线预测总览' })).toBeInTheDocument()
    expect(screenerApi.queryCandidatePool).toHaveBeenCalledWith({ source_module: 'screener', page_size: 20 })
    // 候选池预测排行表渲染候选标的
    expect(screen.getByText('宁德时代')).toBeInTheDocument()
    expect(screen.getByText('比亚迪')).toBeInTheDocument()
    // 候选池条目不冒充预测任务数，真实任务数未持久化时显示 '--'。
    expect(screen.getAllByText('--').length).toBeGreaterThan(0)
    // 摘要只反映候选等级，不伪装为预测结论。
    expect(screen.getByText(/宁德时代 候选等级 S/)).toBeInTheDocument()
    expect(screen.getByText(/比亚迪 候选等级 C/)).toBeInTheDocument()
  })

  it('shows EmptyState when candidate pool has no records on overview', async () => {
    renderPredictions('/predictions')

    expect(await screen.findByText('暂无待预测候选')).toBeInTheDocument()
    // 2 KPI（命中率/预测数）后端字段未齐 → 值 '--'，不展示假数
    expect(screen.getAllByText('--').length).toBeGreaterThan(0)
    // 预警摘要 EmptyState
    expect(screen.getByText('暂无候选输入')).toBeInTheDocument()
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
    // fallback_reason 现同时在「预测 vs 实际走势」EmptyState 与「回测说明」面板出现（5.3 多处诚实降级）
    expect(screen.getAllByText(/awaits persisted prediction labels/).length).toBeGreaterThan(0)
  })

  // 5.1 单股预测：专属渲染对齐 preview —— 30 日 K线路径 + 置信区间 + 信号一致性 + 因子贡献卡片。
  // 后端字段未齐时三卡片走 EmptyState + fallback_reason 不空白（AC③ + AC⑧）。
  it('5.1 single: 渲染预测路径图 + 信号一致性/因子贡献 EmptyState（后端字段未齐诚实降级）', async () => {
    renderPredictions('/predictions/single')

    expect(screen.getByRole('heading', { name: '单股预测' })).toBeInTheDocument()
    // 信号一致性卡片（专属渲染，非通用壳）
    expect(await screen.findByText('信号一致性')).toBeInTheDocument()
    expect(screen.getByText('信号一致性待补齐')).toBeInTheDocument()
    // 因子贡献卡片
    expect(screen.getByText('因子贡献')).toBeInTheDocument()
    expect(screen.getByText('因子贡献待补齐')).toBeInTheDocument()
    // 触发预测后渲染路径图（mock-chart）
    fireEvent.click(screen.getByRole('button', { name: '开始预测' }))
    const charts = await screen.findAllByTestId('mock-chart')
    expect(charts.length).toBeGreaterThanOrEqual(1)
  })

  // 5.2 多股对比：专属渲染对齐 preview —— 对比矩阵 + 置信度列 + 叠加预测曲线。
  it('5.2 compare: 运行对比后渲染对比矩阵 + 置信度列 + 叠加预测曲线图', async () => {
    renderPredictions('/predictions/compare')

    fireEvent.click(await screen.findByRole('button', { name: '运行对比' }))

    await waitFor(() => {
      expect((predictionApi as any).compare).toHaveBeenCalledWith(['300750', '000001', '002594'], 20)
    })
    // 对比矩阵含置信度列头
    expect(await screen.findByText('置信度')).toBeInTheDocument()
    // 叠加预测曲线卡片 + 图表
    expect(screen.getByText('叠加预测曲线（归一化涨跌幅%）')).toBeInTheDocument()
    expect(screen.getAllByTestId('mock-chart').length).toBeGreaterThanOrEqual(1)
  })

  // 5.2 多股对比：空结果走 EmptyState（不空白）
  it('5.2 compare: 未运行对比 → 对比矩阵与叠加曲线均走 EmptyState', async () => {
    renderPredictions('/predictions/compare')

    expect(await screen.findByText('暂无对比结果')).toBeInTheDocument()
    expect(screen.getByText('叠加曲线待对比')).toBeInTheDocument()
  })

  // 5.3 准确率回测：专属渲染对齐 preview —— 4 项统计 + 预测vs实际 EmptyState + 命中序列 EmptyState。
  // 后端逐日序列/逐次命中字段未齐 → 多处 EmptyState + fallback_reason（AC③ + AC⑧）。
  it('5.3 backtest: 渲染预测vs实际 + 命中序列 EmptyState（后端字段未齐诚实降级，不展示假图）', async () => {
    renderPredictions('/predictions/backtest')

    expect(await screen.findByText('预测路径 vs 实际走势 · 偏离区间范围')).toBeInTheDocument()
    // 预测 vs 实际 EmptyState
    expect(screen.getByText('预测 vs 实际走势待补齐')).toBeInTheDocument()
    // 命中序列卡片 + EmptyState
    expect(screen.getByText('最近命中序列')).toBeInTheDocument()
    expect(screen.getByText('命中序列待补齐')).toBeInTheDocument()
    // 平均/最大误差/连对三档 '--' + fallback（不展示假数）
    expect(screen.getAllByText('平均误差').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('最大误差').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('最长连对').length).toBeGreaterThanOrEqual(1)
  })
})
