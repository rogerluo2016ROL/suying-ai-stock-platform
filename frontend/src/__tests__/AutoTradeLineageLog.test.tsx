import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ConfigProvider, App as AntdApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import AutoTrade from '../pages/AutoTrade'

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))

vi.mock('../api/client', () => ({
    default: {
      get: mocks.get,
      post: mocks.post,
      put: vi.fn(),
      delete: vi.fn(),
    },
  }))

function renderAutoTrade(initialEntries = ['/auto-trade']) {
  return render(
    <ConfigProvider locale={zhCN}>
      <AntdApp>
        <MemoryRouter initialEntries={initialEntries}>
          <Routes>
            <Route path="/auto-trade" element={<AutoTrade />} />
            <Route path="/auto-trade/config" element={<AutoTrade />} />
            <Route path="/auto-trade/monitor" element={<AutoTrade />} />
            <Route path="/auto-trade/logs" element={<AutoTrade />} />
            <Route path="/trade/risk-verdicts" element={<div>风控闸门页</div>} />
            <Route path="/trade/decision-contexts" element={<div>决策上下文页</div>} />
          </Routes>
        </MemoryRouter>
      </AntdApp>
    </ConfigProvider>,
  )
}

describe('AutoTrade 自动执行日志 lineage', () => {
  beforeEach(() => {
    mocks.get.mockReset()
    mocks.post.mockReset()
    mocks.post.mockResolvedValue({ data: { status: 'running', message: '策略已启动' } })
    mocks.get.mockImplementation((url: string) => {
      if (url === '/strategy/list') {
        return Promise.resolve({
          data: {
            strategies: [
              {
                id: 'strat-lineage',
                name: '自动龙头策略',
                status: 'active',
                source_type: 'scheme',
                trade_mode: 'paper',
                check_interval_sec: 60,
                capital: 1_000_000,
                picks_count: 1,
                buy_conditions: [],
                sell_conditions: [],
                position_rules: { max_positions: 5, single_max_pct: 0.2, total_position_cap_pct: 0.8 },
                risk_rules: { daily_max_loss_pct: 0.03, stop_loss_pct: 0.03, take_profit_pct: 0.15, trailing_stop_pct: 0 },
                created_at: '2026-06-27T10:00:00Z',
              },
            ],
          },
        })
      }
      if (url === '/strategy/strat-lineage') {
        return Promise.resolve({
          data: {
            id: 'strat-lineage',
            name: '自动龙头策略',
            status: 'active',
            trade_mode: 'paper',
            check_interval_sec: 60,
            capital: 1_000_000,
            picks_count: 1,
            picks: [],
            buy_conditions: [],
            sell_conditions: [],
            position_rules: { max_positions: 5, single_max_pct: 0.2, total_position_cap_pct: 0.8 },
            risk_rules: { daily_max_loss_pct: 0.03, stop_loss_pct: 0.03, take_profit_pct: 0.15, trailing_stop_pct: 0 },
          },
        })
      }
      if (url === '/strategy/strat-lineage/log') {
        return Promise.resolve({
          data: {
            logs: [
              {
                timestamp: '2026-06-27T10:31:00Z',
                level: 'BUY',
                message: '买单已提交: 300750 - order_id=ORD-AUTO',
                details: {
                  code: '300750',
                  order_id: 'ORD-AUTO',
                  decision_context_id: 'CTX-auto-strat-lineage-300750-1',
                  plan_id: 'PLAN-AUTO',
                  candidate_id: 'CAND-300750',
                },
              },
            ],
          },
        })
      }
      return Promise.resolve({ data: {} })
    })
  })

  it('在策略详情日志中展示 lineage 并可跳转风控', async () => {
    const user = userEvent.setup()
    renderAutoTrade()

    await user.click(await screen.findByRole('button', { name: '详情' }))

    expect(await screen.findByText('CTX-auto-strat-lineage-300750-1')).toBeInTheDocument()
    expect(screen.getByText('PLAN-AUTO')).toBeInTheDocument()
    expect(screen.getByText('CAND-300750')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '风控' }))

    expect(screen.getByText('风控闸门页')).toBeInTheDocument()
  })

  it('策略列表失败时不回退演示策略', async () => {
    mocks.get.mockRejectedValue(new Error('strategy down'))
    renderAutoTrade()

    expect(await screen.findByText('暂无自动交易策略。')).toBeInTheDocument()
    expect(screen.queryByText('模拟趋势策略')).not.toBeInTheDocument()
  })

  it('配置页展示策略服务返回的规则', async () => {
    renderAutoTrade(['/auto-trade/config'])

    expect(await screen.findByText('自动龙头策略')).toBeInTheDocument()
    expect(screen.getByText('1000000')).toBeInTheDocument()
    expect(screen.getByText('0.2')).toBeInTheDocument()
    expect(screen.getByText('0.03')).toBeInTheDocument()
  })

  it('启动动作调用策略执行接口', async () => {
    const user = userEvent.setup()
    renderAutoTrade()

    await user.click(await screen.findByRole('button', { name: '启动' }))

    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/strategy/strat-lineage/start?mode=paper'))
    expect(await screen.findByText('策略已启动')).toBeInTheDocument()
  })
})
