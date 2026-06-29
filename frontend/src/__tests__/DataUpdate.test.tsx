import { render, screen, waitFor } from '@testing-library/react'
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
  })

  it('loads data status and schedules through signal service APIs', async () => {
    renderDataUpdate()

    expect(await screen.findByText('日线行情')).toBeInTheDocument()
    expect(await screen.findByText(/1\/1 表正常/)).toBeInTheDocument()
    await waitFor(() => expect(signalApi.getDataStatus).toHaveBeenCalled())
    expect(signalApi.getSyncSchedules).toHaveBeenCalled()
  })

  it('falls back to safe defaults when data status response is partial', async () => {
    vi.mocked(signalApi.getDataStatus).mockResolvedValue({ data: {} } as any)
    vi.mocked(signalApi.getSyncSchedules).mockResolvedValue({ data: {} } as any)

    renderDataUpdate()

    expect(await screen.findByText('日线行情')).toBeInTheDocument()
    expect(await screen.findByText(/3\/4 表正常/)).toBeInTheDocument()
  })
})
