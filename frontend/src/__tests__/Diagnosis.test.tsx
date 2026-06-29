import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Diagnosis from '../pages/Diagnosis'
import { diagnosisApi } from '../api/client'

vi.mock('../api/client', () => ({
  diagnosisApi: {
    getHistory: vi.fn(),
    analyze: vi.fn(),
    compare: vi.fn(),
    getReportPdf: vi.fn(),
  },
}))

function renderDiagnosis(route = '/diagnosis') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Diagnosis />
    </MemoryRouter>,
  )
}

describe('Diagnosis page connectivity', () => {
  beforeEach(() => {
    vi.mocked(diagnosisApi.getHistory).mockResolvedValue({
      data: {
        items: [],
        total: 0,
        page: 1,
        page_size: 20,
      },
    } as any)
    vi.mocked(diagnosisApi.analyze).mockResolvedValue({
      data: {
        code: '000001',
        name: '平安银行',
        overall_score: 76,
        grade: 'B',
        recommendation: '谨慎关注',
        recommendation_reason: '趋势转强但量能不足',
        dimensions: {
          technical: { name: '技术面', score: 78, weight: 0.4, grade: 'B', status: 'watch' },
          money_flow: { name: '资金面', score: 70, weight: 0.3, grade: 'B', status: 'neutral' },
        },
        risk_warnings: ['量能不足'],
      },
    } as any)
    vi.mocked(diagnosisApi.compare).mockResolvedValue({
      data: {
        stocks: [
          { code: '002138', name: '顺络电子', overall_score: 86, grade: 'A', recommendation: '关注', dimensions: {} },
          { code: '300750', name: '宁德时代', overall_score: 72, grade: 'B', recommendation: '观察', dimensions: {} },
        ],
      },
    } as any)
    vi.mocked(diagnosisApi.getReportPdf).mockResolvedValue({ data: new Blob(['pdf']) } as any)
    vi.spyOn(window.URL, 'createObjectURL').mockReturnValue('blob:diagnosis')
    vi.spyOn(window.URL, 'revokeObjectURL').mockImplementation(() => undefined)
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('starts empty instead of using a hard-coded diagnosis stock', async () => {
    renderDiagnosis('/diagnosis')

    await waitFor(() => expect(diagnosisApi.getHistory).toHaveBeenCalled())
    expect(screen.queryByDisplayValue('002138')).not.toBeInTheDocument()
    expect(screen.getAllByText('待输入').length).toBeGreaterThan(0)
  })

  it('runs diagnosis from user input and renders returned dimensions', async () => {
    renderDiagnosis('/diagnosis')

    fireEvent.change(screen.getByLabelText('诊断标的'), { target: { value: '000001' } })
    fireEvent.click(screen.getByRole('button', { name: '开始诊断' }))

    await waitFor(() => expect(diagnosisApi.analyze).toHaveBeenCalledWith('000001'))
    expect(await screen.findByText('平安银行')).toBeInTheDocument()
    expect(screen.getByText('谨慎关注')).toBeInTheDocument()
  })

  it('uses diagnosis compare API for multi-stock comparison', async () => {
    vi.mocked(diagnosisApi.getHistory).mockResolvedValue({
      data: {
        items: [
          { id: 1, code: '002138', name: '顺络电子', overall_score: 86, grade: 'A', created_at: '2026-06-29T09:30:00Z' },
          { id: 2, code: '300750', name: '宁德时代', overall_score: 72, grade: 'B', created_at: '2026-06-29T09:31:00Z' },
        ],
        total: 2,
        page: 1,
        page_size: 20,
      },
    } as any)

    renderDiagnosis('/diagnosis/compare')

    await waitFor(() => expect(diagnosisApi.compare).toHaveBeenCalledWith(['002138', '300750']))
    await waitFor(() => expect(screen.getAllByText('顺络电子').length).toBeGreaterThan(0))
    expect(screen.getAllByText('宁德时代').length).toBeGreaterThan(0)
  })

  it('does not present a risk scan before a report is generated', async () => {
    vi.mocked(diagnosisApi.getHistory).mockResolvedValue({
      data: {
        items: [{ id: 1, code: '002138', name: '顺络电子', overall_score: 86, grade: 'A', created_at: '2026-06-29T09:30:00Z' }],
        total: 1,
        page: 1,
        page_size: 20,
      },
    } as any)

    renderDiagnosis('/diagnosis/risk')

    expect(await screen.findByText('请先生成诊断报告')).toBeInTheDocument()
    expect(screen.queryByText('暂无最新风险警示')).not.toBeInTheDocument()
  })

  it('exports report through diagnosis report API when a real code exists', async () => {
    vi.mocked(diagnosisApi.getHistory).mockResolvedValue({
      data: {
        items: [{ id: 1, code: '002138', name: '顺络电子', overall_score: 86, grade: 'A', created_at: '2026-06-29T09:30:00Z' }],
        total: 1,
        page: 1,
        page_size: 20,
      },
    } as any)

    renderDiagnosis('/diagnosis')

    await screen.findByDisplayValue('002138')
    fireEvent.click(screen.getByRole('button', { name: '导出报告' }))

    await waitFor(() => expect(diagnosisApi.getReportPdf).toHaveBeenCalledWith('002138'))
  })
})
