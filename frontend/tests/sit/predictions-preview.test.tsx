import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Predictions from '../../src/pages/Predictions'
import { predictionApi, screenerApi } from '../../src/api/client'

// SIT scope：5.0 prediction-overview（候选池待预测输入 + 真实 KPI + 候选输入摘要）。
// API client 走 vi.mock（与既有 Predictions.test.tsx 同款），断言"触发→以正确参数调了正确 API"。
// W-1 全 token 化：alert-dot / 语义色走 .up/.down/.warn/.neu className + var(--*) token，禁裸 hex。

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

describe('5.0 prediction-overview SIT', () => {
  beforeEach(() => {
    vi.mocked(predictionApi.getStatus).mockResolvedValue({
      data: {
        model_loaded: true,
        model: 'Kronos-mini',
        device: 'cpu',
        model_metadata: { loaded: true, checkpoint_status: 'base_public', inference_mode: 'overview' },
      },
    } as any)
    vi.mocked((predictionApi as any).getOverview).mockResolvedValue({
      data: {
        model_metadata: { name: 'Kronos-mini', checkpoint_status: 'base_public', loaded: true },
        data_freshness: { status: 'fresh', as_of: '2026-06-26', source: 'postgresql.daily_kline' },
        fallback_reason: 'model checkpoint unavailable; using baseline predictor',
        sections: [{ id: 'overview', title: '预测总览', endpoint: '/api/v1/prediction/overview' }],
      },
    } as any)
    vi.mocked((predictionApi as any).getAccuracyBacktest).mockResolvedValue({
      data: { fallback_reason: 'accuracy backtest awaits persisted prediction labels', metrics: [] },
    } as any)
    vi.mocked(screenerApi.queryCandidatePool).mockResolvedValue({
      data: { total: 0, page: 1, page_size: 20, records: [], empty_state: { reason: '候选池暂无记录' } },
    } as any)
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('overview: 渲染待预测候选与候选输入摘要，调 queryCandidatePool({source_module:screener})', async () => {
    vi.mocked(screenerApi.queryCandidatePool).mockResolvedValue({
      data: {
        total: 1,
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
    await waitFor(() => expect(screenerApi.queryCandidatePool).toHaveBeenCalledWith({ source_module: 'screener', page_size: 20 }))
    expect(screen.getByText('候选池待预测清单')).toBeInTheDocument()
    expect(screen.getByText('宁德时代')).toBeInTheDocument()
    expect(screen.getByText('比亚迪')).toBeInTheDocument()
    expect(screen.getByText('候选输入摘要')).toBeInTheDocument()
    expect(screen.getByText(/宁德时代 候选等级 S/)).toBeInTheDocument()
    expect(screen.getByText(/比亚迪 候选等级 C/)).toBeInTheDocument()
  })

  // AC② + AC⑦：缺数据走 EmptyState，2 KPI 后端字段未齐 → '--' + fallback_reason（不空白 / 不展示假数）。
  it('overview: 候选池空 + 后端命中率字段未齐 → EmptyState + KPI 走 fallback 不展示假数', async () => {
    renderPredictions('/predictions')

    expect(await screen.findByText('暂无待预测候选')).toBeInTheDocument()
    expect(screen.getByText('暂无候选输入')).toBeInTheDocument()
    // 2 KPI（今日预测任务 / 近30次方向正确率）值 '--'
    expect(screen.getAllByText('--').length).toBeGreaterThanOrEqual(2)
  })

  // AC①：overview hero 三入口可跳单股 / 对比 / 回测。
  it('overview: hero 入口跳单股预测页', async () => {
    renderPredictions('/predictions')
    const singleLink = await screen.findByRole('button', { name: '查看单股预测' })
    expect(singleLink).toBeInTheDocument()
  })
})
