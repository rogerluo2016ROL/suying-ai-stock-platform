import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Predictions from '../../src/pages/Predictions'
import { predictionApi } from '../../src/api/client'

// SIT scope：5.1 single-stock + 5.2 multi-compare + 5.3 backtest 三 sub-tab 专属渲染对齐 preview。
// API client 走 vi.mock（与既有 Predictions.test.tsx 同款），断言"触发→以正确参数调了正确 API"。
// W-1 全 token 化：ECharts 色走 lightTokens / alpha(a)（禁裸 hex/rgba）；语义色走 .up/.down/.warn/.neu className。
// 缺数据走 EmptyState + fallback_reason，不空白（AC③ + AC⑧）。

vi.mock('echarts-for-react', () => ({
  default: ({ style }: { style?: React.CSSProperties }) => <div data-testid="mock-chart" style={style} />,
}))

vi.mock('../../src/api/client', () => ({
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

describe('5.1/5.2/5.3 predictions sub-tabs SIT', () => {
  beforeEach(() => {
    vi.mocked(predictionApi.getStatus).mockResolvedValue({
      data: { model_loaded: true, model: 'Kronos-mini', device: 'cpu', model_metadata: { loaded: true, checkpoint_status: 'base_public' } },
    } as any)
    vi.mocked((predictionApi as any).getOverview).mockResolvedValue({
      data: { model_metadata: { name: 'Kronos-mini', checkpoint_status: 'base_public', loaded: true }, fallback_reason: 'baseline predictor' },
    } as any)
    vi.mocked(predictionApi.predict).mockResolvedValue({
      data: {
        code: '300750', name: '宁德时代', current_price: 218.5, pred_last_close: 242.3,
        pred_return_pct: 12.5, confidence: 78, pred_low: 211.8, pred_high: 248.6,
        pred_trajectory: [{ day: 1, open: 218, high: 221, low: 216, close: 220 }],
        model_metadata: { name: 'Kronos-mini', checkpoint_status: 'base_public' },
        data_freshness: { as_of: '2026-06-26', source: 'postgresql.daily_kline' },
        fallback_reason: 'baseline predictor',
      },
    } as any)
    vi.mocked((predictionApi as any).compare).mockResolvedValue({
      data: {
        pred_days: 20,
        items: [
          { code: '300750', name: '宁德时代', current_price: 218.5, pred_last_close: 242.3, pred_return_pct: 12.5, confidence: 78 },
          { code: '000001', name: '平安银行', current_price: 11.2, pred_last_close: 11.8, pred_return_pct: 5.4, confidence: 71 },
        ],
      },
    } as any)
    vi.mocked((predictionApi as any).getAccuracyBacktest).mockResolvedValue({
      data: { fallback_reason: 'accuracy backtest awaits persisted prediction labels', metrics: [] },
    } as any)
    vi.mocked((predictionApi as any).predictFast).mockResolvedValue({ data: { code: '300750' } } as any)
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  // AC① 5.1：单股预测专属渲染——30日 K线路径图 + 置信区间；触发→predict(code, 30) 正确参数。
  it('5.1 single: 点击开始预测 → predict("300750", 30) → 渲染 30日路径图 + 置信区间', async () => {
    renderPredictions('/predictions/single')

    fireEvent.click(screen.getByRole('button', { name: '开始预测' }))

    await waitFor(() => {
      expect(predictionApi.predict).toHaveBeenCalledWith('300750', 30)
    })
    // 30日路径图渲染（mock-chart）
    expect((await screen.findAllByTestId('mock-chart')).length).toBeGreaterThanOrEqual(1)
    // 信号一致性 + 因子贡献专属卡片（后端字段未齐 → EmptyState，不空白）
    expect(screen.getByText('信号一致性')).toBeInTheDocument()
    expect(screen.getByText('因子贡献')).toBeInTheDocument()
  })

  // AC② 5.2：多股对比专属渲染——对比矩阵（置信度列）+ 叠加预测曲线；触发→compare(codes, 20) 正确参数。
  it('5.2 compare: 点击运行对比 → compare(["300750","000001","002594"], 20) → 渲染矩阵 + 置信度列 + 叠加曲线', async () => {
    renderPredictions('/predictions/compare')

    fireEvent.click(await screen.findByRole('button', { name: '运行对比' }))

    await waitFor(() => {
      expect((predictionApi as any).compare).toHaveBeenCalledWith(['300750', '000001', '002594'], 20)
    })
    // 对比矩阵含置信度列
    expect(await screen.findByText('置信度')).toBeInTheDocument()
    // 叠加预测曲线专属图
    expect(screen.getByText('叠加预测曲线（归一化涨跌幅%）')).toBeInTheDocument()
    expect(screen.getAllByTestId('mock-chart').length).toBeGreaterThanOrEqual(1)
  })

  // AC③ 5.3：准确率回测专属渲染——预测vs实际 + 命中序列 EmptyState（后端逐日/逐次字段未齐诚实降级）。
  it('5.3 backtest: 进入即调 getAccuracyBacktest → 预测vs实际/命中序列 EmptyState + 4项统计占位', async () => {
    renderPredictions('/predictions/backtest')

    await waitFor(() => {
      expect((predictionApi as any).getAccuracyBacktest).toHaveBeenCalled()
    })
    // 预测 vs 实际走势 EmptyState（不展示假图）
    expect(await screen.findByText('预测 vs 实际走势待补齐')).toBeInTheDocument()
    // 命中序列 EmptyState
    expect(screen.getByText('命中序列待补齐')).toBeInTheDocument()
    // 4 项统计占位（方向正确率/平均误差/最大误差/最长连对）
    expect(screen.getAllByText('平均误差').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('最长连对').length).toBeGreaterThanOrEqual(1)
  })

  // AC④ 三 sub-tab 专属渲染（非通用壳）—— 切换 tab 渲染各自专属标题。
  it('AC④ 三 sub-tab 专属渲染：single/compare/backtest 各有专属区块标题', async () => {
    const { unmount } = renderPredictions('/predictions/single')
    expect(screen.getByRole('heading', { name: '单股预测' })).toBeInTheDocument()
    expect(screen.getByText('信号一致性')).toBeInTheDocument()
    unmount()

    const { unmount: u2 } = renderPredictions('/predictions/compare')
    expect(screen.getByRole('heading', { name: '多股对比' })).toBeInTheDocument()
    expect(screen.getByText('叠加预测曲线（归一化涨跌幅%）')).toBeInTheDocument()
    u2()

    renderPredictions('/predictions/backtest')
    expect(screen.getByRole('heading', { name: '准确率回测' })).toBeInTheDocument()
    expect(screen.getByText('最近命中序列')).toBeInTheDocument()
  })
})
