import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Diagnosis from '../pages/Diagnosis'
import Training from '../pages/Training'
import ModelRegistry from '../pages/ModelRegistry'
import RuntimeStatus from '../pages/RuntimeStatus'
import PlatformUpgrade from '../pages/PlatformUpgrade'
import { diagnosisApi, healthApi, trainingApi } from '../api/client'
import { liveTradeApi } from '../api/liveTrade'

vi.mock('../api/client', () => ({
  healthApi: {
    gateway: vi.fn(),
    check: vi.fn(),
  },
  trainingApi: {
    archiveModel: vi.fn(),
    deployModel: vi.fn(),
    getHistory: vi.fn(),
    getModel: vi.fn(),
    getModels: vi.fn(),
    getSchedule: vi.fn(),
    rollbackModel: vi.fn(),
  },
  diagnosisApi: {
    getHistory: vi.fn(),
    analyze: vi.fn(),
    compare: vi.fn(),
    getReportPdf: vi.fn(),
  },
}))

vi.mock('../api/liveTrade', () => ({
  liveTradeApi: {
    getBrokerStatus: vi.fn(),
    getRiskConfig: vi.fn(),
  },
}))

function renderPage(page: React.ReactNode, route: string) {
  return render(<MemoryRouter initialEntries={[route]}>{page}</MemoryRouter>)
}

describe('Phase 5 system pages', () => {
  beforeEach(() => {
    vi.mocked(trainingApi.getHistory).mockResolvedValue({
      data: {
        jobs: [{
          job_id: 'TRN-live-001',
          model_type: 'kronos_finetune',
          status: 'running',
          params: { dataset: 'daily-v20260629', epochs: 8 },
          final_metrics: { ic: 0.13, sharpe: 1.42 },
          created_by: 'admin',
          created_at: '2026-06-29T08:00:00Z',
          started_at: '2026-06-29T08:05:00Z',
        }],
        total: 1,
        page: 1,
        page_size: 20,
      },
    } as any)
    vi.mocked(trainingApi.getModels).mockResolvedValue({
      data: {
        models: [{
          id: 'mdl-alpha-v3',
          name: 'alpha-ranker',
          version: 3,
          model_type: 'lightgbm',
          stage: 'production',
          metrics: { ic: 0.13, sharpe: 1.42 },
          created_by: 'admin',
          created_at: '2026-06-29T08:30:00Z',
        }],
        total: 1,
        page: 1,
        page_size: 20,
      },
    } as any)
    vi.mocked((trainingApi as any).getModel).mockResolvedValue({
      data: {
        id: 'mdl-alpha-v3',
        name: 'alpha-ranker',
        version: 3,
        model_type: 'lightgbm',
        stage: 'production',
        metrics: { ic: 0.13, sharpe: 1.42 },
        created_by: 'admin',
        created_at: '2026-06-29T08:30:00Z',
      },
    } as any)
    vi.mocked((trainingApi as any).deployModel).mockResolvedValue({ data: { message: '已上线' } } as any)
    vi.mocked((trainingApi as any).rollbackModel).mockResolvedValue({ data: { message: '已回滚' } } as any)
    vi.mocked((trainingApi as any).archiveModel).mockResolvedValue({ data: { message: '已归档' } } as any)
    vi.mocked(trainingApi.getSchedule).mockResolvedValue({
      data: {
        enabled: true,
        cron: '30 15 * * 5',
        model_type: 'lightgbm',
        auto_deploy: false,
        next_run: '2026-07-03T15:30:00Z',
        last_job_id: 'TRN-live-001',
        last_job_status: 'running',
      },
    } as any)
    vi.mocked(healthApi.gateway).mockResolvedValue({ data: { status: 'healthy', service: 'gateway' } } as any)
    vi.mocked(healthApi.check).mockResolvedValue({ data: { status: 'healthy', service: 'service', version: '0.1.0' } } as any)
    vi.mocked(liveTradeApi.getBrokerStatus).mockResolvedValue({ data: { mode: 'paper', broker_name: 'mock_qmt', connected: true } } as any)
    vi.mocked(liveTradeApi.getRiskConfig).mockResolvedValue({ data: { max_position_pct: 0.2, max_single_amount: 100000 } } as any)
    vi.mocked(diagnosisApi.getHistory).mockResolvedValue({
      data: {
        items: [{
          id: 1,
          code: '002138',
          name: '顺络电子',
          overall_score: 86,
          grade: 'A',
          created_at: '2026-06-29T09:30:00Z',
        }],
        total: 1,
        page: 1,
        page_size: 20,
      },
    } as any)
    vi.mocked(diagnosisApi.analyze).mockResolvedValue({
      data: {
        code: '002138',
        name: '顺络电子',
        overall_score: 86,
        grade: 'A',
        recommendation: '关注',
        dimensions: {},
      },
    } as any)
    vi.mocked(diagnosisApi.compare).mockResolvedValue({
      data: {
        stocks: [],
        comparison_table: {},
      },
    } as any)
    vi.mocked(diagnosisApi.getReportPdf).mockResolvedValue({ data: new Blob(['pdf']) } as any)
  })

  it('renders diagnosis as concrete five-dimension analysis', () => {
    renderPage(<Diagnosis />, '/diagnosis/overview')

    expect(screen.getByRole('heading', { name: '个股诊断 - 综合诊断' })).toBeInTheDocument()
    expect(screen.getByText('五维评分')).toBeInTheDocument()
    expect(screen.queryByText('个股诊断骨架')).not.toBeInTheDocument()
  })

  it('loads diagnosis history from diagnosis service API', async () => {
    renderPage(<Diagnosis />, '/diagnosis/compare')

    expect((await screen.findAllByText('顺络电子')).length).toBeGreaterThan(0)
    await waitFor(() => expect(diagnosisApi.getHistory).toHaveBeenCalled())
  })

  it('renders model training and registry without skeleton copy', () => {
    renderPage(<Training />, '/training/tasks')
    expect(screen.getByRole('heading', { name: '模型训练 - 训练任务' })).toBeInTheDocument()
    expect(screen.getByText('训练任务队列')).toBeInTheDocument()
    expect(screen.queryByText('模型训练骨架')).not.toBeInTheDocument()

    renderPage(<ModelRegistry />, '/model-registry')
    expect(screen.getByRole('heading', { name: '模型注册 - 版本治理' })).toBeInTheDocument()
    expect(screen.getByText('生产模型注册表')).toBeInTheDocument()
    expect(screen.queryByText('模型注册骨架')).not.toBeInTheDocument()
  })

  it('loads training and model registry data from training service APIs', async () => {
    renderPage(<Training />, '/training/tasks')

    expect((await screen.findAllByText('TRN-live-001')).length).toBeGreaterThan(0)
    expect(await screen.findByText('kronos_finetune')).toBeInTheDocument()
    await waitFor(() => expect(trainingApi.getHistory).toHaveBeenCalled())
    expect(trainingApi.getModels).toHaveBeenCalled()
    expect(trainingApi.getSchedule).toHaveBeenCalled()

    renderPage(<ModelRegistry />, '/model-registry')
    expect(await screen.findByText('alpha-ranker')).toBeInTheDocument()
  })

  it('renders model registry empty state without fake model rows', async () => {
    vi.mocked(trainingApi.getModels).mockResolvedValueOnce({
      data: { models: [], total: 0, page: 1, page_size: 20 },
    } as any)

    renderPage(<ModelRegistry />, '/model-registry')

    expect(await screen.findByText('暂无注册模型')).toBeInTheDocument()
    expect(screen.queryByText('暂无 training/models 返回的模型。')).not.toBeInTheDocument()
  })

  it('deploys candidate model through training service API', async () => {
    vi.mocked(trainingApi.getModels).mockResolvedValue({
      data: {
        models: [
          {
            id: 'mdl-alpha-v3',
            name: 'alpha-ranker',
            version: 3,
            model_type: 'lightgbm',
            stage: 'production',
            metrics: { ic: 0.13 },
            created_by: 'admin',
            created_at: '2026-06-29T08:30:00Z',
          },
          {
            id: 'mdl-alpha-v4',
            name: 'alpha-ranker',
            version: 4,
            model_type: 'lightgbm',
            stage: 'candidate',
            metrics: { ic: 0.18 },
            created_by: 'admin',
            created_at: '2026-06-29T09:30:00Z',
          },
        ],
        total: 2,
        page: 1,
        page_size: 20,
      },
    } as any)

    renderPage(<ModelRegistry />, '/model-registry')

    fireEvent.click(await screen.findByRole('button', { name: /上线候选模型/ }))

    await waitFor(() => expect((trainingApi as any).deployModel).toHaveBeenCalledWith(
      'mdl-alpha-v4',
      expect.objectContaining({ force: false }),
    ))
  })

  it('loads runtime service health from health APIs', async () => {
    renderPage(<RuntimeStatus />, '/runtime')

    expect(await screen.findByText('api-gateway')).toBeInTheDocument()
    await waitFor(() => expect(healthApi.gateway).toHaveBeenCalled())
    expect(healthApi.check).toHaveBeenCalledWith('training')
  })

  it('marks training service outage as a runtime anomaly', async () => {
    vi.mocked(healthApi.check).mockImplementation((service: string) => {
      if (service === 'training') return Promise.reject(new Error('training offline'))
      return Promise.resolve({ data: { status: 'healthy', service, version: '0.1.0' } } as any)
    })

    renderPage(<RuntimeStatus />, '/runtime')

    expect(await screen.findByText('training-service')).toBeInTheDocument()
    await waitFor(() => expect(screen.getAllByText('offline').length).toBeGreaterThan(0))
    expect(screen.getByText('模型服务异常')).toBeInTheDocument()
  })

  it('renders runtime and platform upgrade governance views', () => {
    renderPage(<RuntimeStatus />, '/runtime')
    expect(screen.getByText('服务健康矩阵')).toBeInTheDocument()

    renderPage(<PlatformUpgrade />, '/platform-upgrade')
    expect(screen.getByText('多租户升级矩阵')).toBeInTheDocument()
    expect(screen.getByText('公共数据 / 私有对象边界')).toBeInTheDocument()
  })

  it('loads platform upgrade governance state from health, training and trade APIs', async () => {
    renderPage(<PlatformUpgrade />, '/platform-upgrade')

    expect((await screen.findAllByText('paper')).length).toBeGreaterThan(0)
    await waitFor(() => expect(healthApi.gateway).toHaveBeenCalled())
    expect(healthApi.check).toHaveBeenCalledWith('auth')
    expect(healthApi.check).toHaveBeenCalledWith('trade')
    expect(healthApi.check).toHaveBeenCalledWith('training')
    expect(trainingApi.getModels).toHaveBeenCalledWith({ page: 1, page_size: 20 })
    expect(liveTradeApi.getBrokerStatus).toHaveBeenCalled()
    expect(liveTradeApi.getRiskConfig).toHaveBeenCalled()
  })

  it('does not assume paper broker mode when broker status fails', async () => {
    vi.mocked(liveTradeApi.getBrokerStatus).mockRejectedValueOnce(new Error('broker unavailable'))

    renderPage(<PlatformUpgrade />, '/platform-upgrade')

    expect(await screen.findByText('券商模式')).toBeInTheDocument()
    await waitFor(() => expect(liveTradeApi.getBrokerStatus).toHaveBeenCalled())
    expect(screen.queryByText('Paper')).not.toBeInTheDocument()
    expect(screen.getAllByText('未知').length).toBeGreaterThan(0)
  })
})
