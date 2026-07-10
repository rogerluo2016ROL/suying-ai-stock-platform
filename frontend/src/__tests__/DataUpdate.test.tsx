import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { MemoryRouter } from 'react-router-dom'
import DataUpdate from '../pages/DataUpdate'
import { signalApi } from '../api/client'

vi.mock('../api/client', () => ({
  signalApi: {
    getDataStatus: vi.fn(),
    triggerSync: vi.fn(),
    getSyncSchedules: vi.fn(),
    updateSyncSchedules: vi.fn(),
    deleteSyncSchedule: vi.fn(),
  },
}))

function renderDataUpdate() {
  return render(
    <ConfigProvider locale={zhCN}>
      <MemoryRouter initialEntries={['/data-update']}>
        <DataUpdate />
      </MemoryRouter>
    </ConfigProvider>,
  )
}

describe('DataUpdate', () => {
  beforeEach(() => {
    vi.mocked(signalApi.getDataStatus).mockResolvedValue({
      data: {
        status: 'ok',
        total_tables: 1,
        active_tables: 1,
        total_rows: 1200,
        sources: [{
          key: 'daily_kline',
          name: '日线行情',
          category: '行情',
          source: 'Tushare',
          update: '每日',
          note: 'A股日线',
          rows: 1200,
          min_date: '2026-01-01',
          max_date: '2026-06-27',
          status: 'active',
        }],
        sync_map: {
          daily_kline: { mode: 'post_market', days_default: 30, desc: '日线行情' },
        },
      },
    } as any)
    vi.mocked(signalApi.getSyncSchedules).mockResolvedValue({
      data: { status: 'ok', schedules: [] },
    } as any)
    vi.mocked(signalApi.triggerSync).mockResolvedValue({
      data: { status: 'ok', table_key: 'daily_kline', mode: 'daily_kline', days: 30, output: ['done'] },
    } as any)
  })

  it('loads data status and schedules through signal service APIs', async () => {
    renderDataUpdate()

    expect(await screen.findByText('日线行情')).toBeInTheDocument()
    expect(await screen.findByText(/1\/1 表正常/)).toBeInTheDocument()
    await waitFor(() => expect(signalApi.getDataStatus).toHaveBeenCalled())
    expect(signalApi.getSyncSchedules).toHaveBeenCalled()
  })

  it('fills only structural defaults when data status response is partial', async () => {
    vi.mocked(signalApi.getDataStatus).mockResolvedValue({ data: {} } as any)
    vi.mocked(signalApi.getSyncSchedules).mockResolvedValue({ data: {} } as any)

    renderDataUpdate()

    expect(await screen.findByText('数据状态不可用')).toBeInTheDocument()
    expect(screen.getByText(/数据状态未知/)).toBeInTheDocument()
    expect(screen.queryByText('日线行情')).not.toBeInTheDocument()
    expect(screen.queryByText('2026-06-27')).not.toBeInTheDocument()
  })

  it('downgrades an incomplete ok data status response to unavailable', async () => {
    vi.mocked(signalApi.getDataStatus).mockResolvedValue({ data: { status: 'ok' } } as any)

    renderDataUpdate()

    expect(await screen.findByText('数据状态不可用')).toBeInTheDocument()
    expect(screen.getByText('数据状态响应结构不完整')).toBeInTheDocument()
    expect(screen.getByText(/数据状态未知/)).toBeInTheDocument()
    expect(screen.queryByText(/0\/0 表正常/)).not.toBeInTheDocument()
    expect(screen.queryByText('所有表正常')).not.toBeInTheDocument()
  })

  it('does not show demo row counts when data status fails', async () => {
    vi.mocked(signalApi.getDataStatus).mockRejectedValueOnce(new Error('gateway unavailable'))

    renderDataUpdate()

    expect(await screen.findByText('数据状态不可用')).toBeInTheDocument()
    expect(screen.getByText('gateway unavailable')).toBeInTheDocument()
    expect(screen.queryByText('982,000')).not.toBeInTheDocument()
    expect(screen.queryByText('2026-06-27')).not.toBeInTheDocument()
  })

  it('keeps real data status when the schedule request is unavailable', async () => {
    vi.mocked(signalApi.getSyncSchedules).mockRejectedValueOnce(new Error('schedule gateway unavailable'))

    renderDataUpdate()

    expect(await screen.findByText(/1\/1 表正常/)).toBeInTheDocument()
    expect(screen.getByText('同步调度不可用')).toBeInTheDocument()
    expect(screen.getByText('schedule gateway unavailable')).toBeInTheDocument()
    expect(screen.getByText('调度状态未知')).toBeInTheDocument()
    expect(screen.queryByText('数据状态不可用')).not.toBeInTheDocument()
  })

  it('keeps real data status when the schedule API returns an error status', async () => {
    vi.mocked(signalApi.getSyncSchedules).mockResolvedValueOnce({
      data: { status: 'error', message: 'scheduler disabled', schedules: [] },
    } as any)

    renderDataUpdate()

    expect(await screen.findByText(/1\/1 表正常/)).toBeInTheDocument()
    expect(screen.getByText('同步调度返回错误')).toBeInTheDocument()
    expect(screen.getByText('scheduler disabled')).toBeInTheDocument()
    expect(screen.getByText('调度状态未知')).toBeInTheDocument()
    expect(screen.queryByText('数据状态不可用')).not.toBeInTheDocument()
  })

  it('can refresh status and trigger a manual sync for a table', async () => {
    renderDataUpdate()

    await waitFor(() => expect(signalApi.getDataStatus).toHaveBeenCalled())
    const beforeRefreshCalls = vi.mocked(signalApi.getDataStatus).mock.calls.length
    fireEvent.click(await screen.findByRole('button', { name: /刷新状态/ }))
    await waitFor(() => expect(signalApi.getDataStatus).toHaveBeenCalledTimes(beforeRefreshCalls + 1))

    fireEvent.click((await screen.findAllByRole('button', { name: /同步日线行情/ }))[0])
    await waitFor(() => expect(signalApi.triggerSync).toHaveBeenCalledWith('daily_kline', 30))
    expect(await screen.findByText(/daily_kline 同步已触发/)).toBeInTheDocument()
  })

  it('uses daily kline as the page trade date when financial data has a future period', async () => {
    vi.mocked(signalApi.getDataStatus).mockResolvedValue({
      data: {
        status: 'ok',
        total_tables: 2,
        active_tables: 2,
        total_rows: 2200,
        sources: [
          {
            key: 'daily_kline',
            name: '日线行情',
            category: '行情',
            source: 'Tushare',
            update: '每日',
            note: 'A股日线',
            rows: 1200,
            min_date: '2026-01-01',
            max_date: '2026-06-29',
            status: 'active',
          },
          {
            key: 'forecast_data',
            name: '业绩预告',
            category: '财务',
            source: 'Tushare forecast',
            update: '不定期',
            note: '',
            rows: 1000,
            min_date: '2021-03-31',
            max_date: '2027-12-31',
            status: 'active',
          },
        ],
        sync_map: {
          daily_kline: { mode: 'post_market', days_default: 30, desc: '日线行情' },
          forecast_data: { mode: 'forecast', days_default: 365, desc: '业绩预告' },
        },
      },
    } as any)

    renderDataUpdate()

    expect(await screen.findByText('交易日：2026-06-29')).toBeInTheDocument()
    expect(screen.queryByText('交易日：2027-12-31')).not.toBeInTheDocument()
  })
})
