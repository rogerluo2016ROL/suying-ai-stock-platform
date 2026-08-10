import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ConfigProvider, App as AntdApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import AutoTrade from '../pages/AutoTrade'

const mocks = vi.hoisted(() => ({
  listInstances: vi.fn(),
  getInstance: vi.fn(),
  getInstanceLog: vi.fn(),
  startInstance: vi.fn(),
  pauseInstance: vi.fn(),
  resumeInstance: vi.fn(),
  stopInstance: vi.fn(),
  getTemplates: vi.fn(),
  createPlan: vi.fn(),
  updateInstance: vi.fn(),
}))

vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="echarts" />,
}))

vi.mock('../api/client', () => ({
    default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
    strategyApi: {
      listInstances: mocks.listInstances,
      getInstance: mocks.getInstance,
      getInstanceLog: mocks.getInstanceLog,
      startInstance: mocks.startInstance,
      pauseInstance: mocks.pauseInstance,
      resumeInstance: mocks.resumeInstance,
      stopInstance: mocks.stopInstance,
      getTemplates: mocks.getTemplates,
      createPlan: mocks.createPlan,
      updateInstance: mocks.updateInstance,
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
    Object.values(mocks).forEach(m => m.mockReset())
    mocks.startInstance.mockResolvedValue({ data: { status: 'running', message: '策略已启动' } })
    mocks.listInstances.mockResolvedValue({
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
    mocks.getInstance.mockResolvedValue({
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
    mocks.getInstanceLog.mockResolvedValue({
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
    mocks.getTemplates.mockResolvedValue({
      data: {
        templates: [
          { id: 'aggressive', name: '激进型', risk: 'high', max_positions: 3, single_max: 0.2, description: '高弹性龙头模板' },
          { id: 'balanced', name: '均衡型', risk: 'medium', max_positions: 5, single_max: 0.12 },
        ],
      },
    })
    mocks.createPlan.mockResolvedValue({
      data: { plan: { id: 'plan-follow-1', name: '激进型 跟单', model_name: 'aggressive', max_positions: 3, capital: 1_000_000 } },
    })
    mocks.updateInstance.mockResolvedValue({
      data: {
        strategy: {
          id: 'strat-lineage',
          name: '自动龙头策略',
          capital: 1_000_000,
          position_rules: { max_positions: 6, single_max_pct: 0.2, total_position_cap_pct: 0.8 },
        },
        message: '策略已更新',
      },
    })
  })

  it('在策略详情日志中展示 lineage 并可跳转风控', async () => {
    const user = userEvent.setup()
    renderAutoTrade(['/auto-trade/monitor'])

    await user.click(await screen.findByRole('button', { name: '详情' }))

    expect(await screen.findByText('CTX-auto-strat-lineage-300750-1')).toBeInTheDocument()
    expect(screen.getByText('PLAN-AUTO')).toBeInTheDocument()
    expect(screen.getByText('CAND-300750')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '风控' }))

    expect(screen.getByText('风控闸门页')).toBeInTheDocument()
  })

  it('策略列表失败时不回退演示策略', async () => {
    mocks.listInstances.mockRejectedValue(new Error('strategy down'))
    renderAutoTrade(['/auto-trade/monitor'])

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
    renderAutoTrade(['/auto-trade/monitor'])

    await user.click(await screen.findByRole('button', { name: '启动' }))

    await waitFor(() => expect(mocks.startInstance).toHaveBeenCalledWith('strat-lineage'))
    expect(await screen.findByText('策略已启动')).toBeInTheDocument()
  })

  it('策略广场展示模板并通过一键跟单创建方案', async () => {
    const user = userEvent.setup()
    renderAutoTrade()

    expect(await screen.findByText('激进型')).toBeInTheDocument()
    expect(screen.getByText('均衡型')).toBeInTheDocument()

    await user.click(screen.getAllByRole('button', { name: '一键跟单' })[0])
    await user.click(await screen.findByRole('button', { name: '确认跟单' }))

    await waitFor(() => expect(mocks.createPlan).toHaveBeenCalledWith('激进型 跟单', 'aggressive', 3, 1_000_000))
    expect(await screen.findByText(/一键跟单成功/)).toBeInTheDocument()
  })

  it('策略广场支持按模型类型筛选', async () => {
    const user = userEvent.setup()
    renderAutoTrade()

    await screen.findByText('激进型')
    await user.selectOptions(screen.getByLabelText('模型类型筛选'), 'high')

    expect(screen.getByText('激进型')).toBeInTheDocument()
    expect(screen.queryByText('均衡型')).not.toBeInTheDocument()
  })

  it('配置页可编辑最大持仓并调用更新接口', async () => {
    const user = userEvent.setup()
    renderAutoTrade(['/auto-trade/config'])

    const input = await screen.findByLabelText('最大持仓数')
    await user.clear(input)
    await user.type(input, '6')
    await user.click(screen.getByRole('button', { name: '保存配置' }))

    await waitFor(() => expect(mocks.updateInstance).toHaveBeenCalledWith('strat-lineage', {
      capital: 1_000_000,
      position_rules: { max_positions: 6, single_max_pct: 0.2, total_position_cap_pct: 0.8 },
    }))
  })

  it('日志页支持按级别筛选', async () => {
    mocks.getInstanceLog.mockResolvedValue({
      data: {
        logs: [
          { timestamp: '2026-06-27T10:31:00Z', level: 'BUY', message: '买单已提交: 300750', details: {} },
          { timestamp: '2026-06-27T11:00:00Z', level: 'SELL', message: '卖单已提交: 300750', details: {} },
        ],
      },
    })
    const user = userEvent.setup()
    renderAutoTrade(['/auto-trade/logs'])

    expect(await screen.findByText('买单已提交: 300750')).toBeInTheDocument()
    expect(screen.getByText('卖单已提交: 300750')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'BUY' }))
    expect(screen.getByText('买单已提交: 300750')).toBeInTheDocument()
    expect(screen.queryByText('卖单已提交: 300750')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'SELL' }))
    expect(screen.getByText('卖单已提交: 300750')).toBeInTheDocument()
    expect(screen.queryByText('买单已提交: 300750')).not.toBeInTheDocument()
  })
})
