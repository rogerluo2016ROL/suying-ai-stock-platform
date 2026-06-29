import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { MemoryRouter } from 'react-router-dom'
import Screener from '../pages/Screener'
import { screenerApi, signalApi } from '../api/client'

vi.mock('../api/client', () => ({
  screenerApi: {
    getModes: vi.fn(),
    run: vi.fn(),
  },
  signalApi: {
    triggerSync: vi.fn(),
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
    vi.mocked(signalApi.triggerSync).mockResolvedValue({
      data: { status: 'ok' },
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

    fireEvent.change(screen.getByLabelText('选股日期'), { target: { value: '2026-06-26' } })
    fireEvent.change(screen.getByLabelText('Top 数量'), { target: { value: '30' } })
    fireEvent.click(screen.getByRole('button', { name: /开始选股/ }))

    expect(await screen.findByText('光迅科技')).toBeInTheDocument()
    await waitFor(() => {
      expect(signalApi.triggerSync).toHaveBeenCalledWith('stk_auction_o', 1)
      expect(screenerApi.run).toHaveBeenCalledWith('leader_auction', 30, '2026-06-26')
    })
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

  it('matches the screener workbench prototype structure', async () => {
    render(
      <ConfigProvider locale={zhCN}>
        <MemoryRouter>
          <Screener />
        </MemoryRouter>
      </ConfigProvider>,
    )

    expect(screen.getByLabelText('模型分类页签')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /趋势 \/ 秋神/ })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /多因子 \/ 主题型/ })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /可转债/ })).toBeInTheDocument()
    expect(screen.getByText('秋神竞价超预期选股')).toBeInTheDocument()
    expect(screen.getByText('秋神午后选股模型')).toBeInTheDocument()
    expect(screen.getByText('毕师傅全市场 V1.0')).toBeInTheDocument()
    expect(screen.getByText('日期')).toBeInTheDocument()
    expect(screen.getByLabelText('选股日期')).toHaveValue('2026-06-26')
    expect(screen.getByLabelText('Top 数量')).toHaveValue('20')
    expect(screen.getByRole('button', { name: /运行选股/ })).toBeInTheDocument()
    expect(screen.getByText('数据更新')).toBeInTheDocument()
    expect(screen.getByText('模型选股')).toBeInTheDocument()
    expect(screen.getByText('输出股票')).toBeInTheDocument()
    expect(screen.getByText('市值(亿)')).toBeInTheDocument()
    expect(screen.getByText('秋神竞价超预期分析')).toBeInTheDocument()
    expect(screen.getByText('竞价指标')).toBeInTheDocument()
    expect(screen.getByText('高开%')).toBeInTheDocument()
    expect(screen.getByText(/ST风险: 通过/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '加入候选池 →' })).toBeInTheDocument()
  })
})
