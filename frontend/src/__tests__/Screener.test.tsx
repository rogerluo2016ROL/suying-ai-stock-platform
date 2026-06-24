import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { MemoryRouter } from 'react-router-dom'
import Screener from '../pages/Screener'
import { screenerApi } from '../api/client'

vi.mock('../api/client', () => ({
  screenerApi: {
    getModes: vi.fn(),
    run: vi.fn(),
  },
  strategyApi: {
    createPlan: vi.fn(),
    addPicks: vi.fn(),
  },
}))

describe('Screener', () => {
  beforeEach(() => {
    vi.mocked(screenerApi.getModes).mockResolvedValue({
      data: {
        modes: [
          { id: 'bi_trend_launch', name: '毕师傅趋势启动', cycle: '短线' },
        ],
      },
    } as any)
    vi.mocked(screenerApi.run).mockResolvedValue({
      data: {
        market_env: 'neutral',
        total_scored: 1,
        total_excluded: 0,
        elapsed: 1.2,
        picks: [{
          code: '002281',
          name: '光迅科技',
          price: 88.5,
          score: 86,
          grade: 'S',
          signal: 'watch',
          hard_tech: {
            track: 'AI算力',
            tier: 'core',
            matched_keywords: ['算力', '芯片', '通信'],
            chokepoint_level: 'normal',
          },
          factor_breakdown: {
            startup_quality: -7,
            ignition_power: 0,
            hard_tech_conviction: 4,
          },
          entry_reason: '硬科技: AI算力(core)；风险: late_rebound、ma20_extension',
          risk_flags: ['late_rebound', 'ma20_extension'],
          power_flags: [],
        }],
      },
    } as any)
  })

  it('shows Bi trend hard-tech track, reason, and four-axis flags', async () => {
    render(
      <ConfigProvider locale={zhCN}>
        <MemoryRouter>
          <Screener />
        </MemoryRouter>
      </ConfigProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: /开始选股/ }))

    expect(await screen.findByText('光迅科技')).toBeInTheDocument()
    expect(screen.getByText('AI算力')).toBeInTheDocument()
    expect(screen.getByText('core')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /展开四轴解释/ }))

    await waitFor(() => {
      expect(screen.getByText(/硬科技: AI算力/)).toBeInTheDocument()
    })
    expect(screen.getByText('late_rebound')).toBeInTheDocument()
    expect(screen.getByText('ma20_extension')).toBeInTheDocument()
    expect(screen.getByText('硬科技 4.0')).toBeInTheDocument()
    expect(screen.getByText('启动质量 -7.0')).toBeInTheDocument()
  })
})
