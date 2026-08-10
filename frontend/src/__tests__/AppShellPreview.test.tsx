import { render, screen, waitFor, within } from '@testing-library/react'
import { ConfigProvider, App as AntdApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { MemoryRouter } from 'react-router-dom'
import type { AuthContextValue } from '../contexts/AuthContext'
import App from '../App'

const mockUseAuth = vi.fn<() => AuthContextValue>()

vi.mock('../contexts/AuthContext', async () => {
  const actual = await vi.importActual<typeof import('../contexts/AuthContext')>('../contexts/AuthContext')
  return {
    ...actual,
    useAuth: () => mockUseAuth(),
  }
})

vi.mock('../contexts/ThemeContext', () => ({
  useTheme: () => ({
    mode: 'light',
    setMode: vi.fn(),
  }),
}))

vi.mock('../api/client', () => ({
  alertApi: {
    getUnreadCount: vi.fn().mockResolvedValue({ data: { unread: 3 } }),
  },
  marketApi: {
    getIndexQuotes: vi.fn().mockResolvedValue({
      data: {
        data: {
          diff: [
            { f12: '000001', f2: 4075.5, f3: -0.9 },
            { f12: '399001', f2: 15794.7, f3: -2.01 },
            { f12: '399006', f2: 4121.09, f3: -3.28 },
            { f12: '899050', f2: 1294.82, f3: 2.36 },
          ],
        },
      },
    }),
  },
  clearPlatformContext: vi.fn(),
  injectPlatformContext: vi.fn(),
}))

vi.mock('../pages/Dashboard', () => ({ default: () => <div>看板内容</div> }))
vi.mock('../pages/Screener', () => ({ default: () => <div>选股内容</div> }))
vi.mock('../pages/SupplyChainBom', () => ({ default: () => <div>产业链内容</div> }))
vi.mock('../pages/Predictions', () => ({ default: () => <div>预测内容</div> }))
vi.mock('../pages/Signals', () => ({ default: () => <div>信号内容</div> }))
vi.mock('../pages/Trade', () => ({ default: () => <div>交易内容</div> }))
vi.mock('../pages/AuditLog', () => ({ default: () => <div>审计内容</div> }))
vi.mock('../pages/RiskVerdicts', () => ({ default: () => <div>风控内容</div> }))
vi.mock('../pages/DecisionContexts', () => ({ default: () => <div>决策上下文内容</div> }))
vi.mock('../pages/Diagnosis', () => ({ default: () => <div>诊断内容</div> }))
vi.mock('../pages/Backtest', () => ({ default: () => <div>回测内容</div> }))
vi.mock('../pages/Strategy', () => ({ default: () => <div>方案内容</div> }))
vi.mock('../pages/AutoTrade', () => ({ default: () => <div>量化内容</div> }))
vi.mock('../pages/Training', () => ({ default: () => <div>训练内容</div> }))
vi.mock('../pages/ModelRegistry', () => ({ default: () => <div>模型内容</div> }))
vi.mock('../pages/DataUpdate', () => ({ default: () => <div>数据内容</div> }))

function renderShell(initialRoute = '/') {
  return render(
    <ConfigProvider locale={zhCN}>
      <AntdApp>
        <MemoryRouter initialEntries={[initialRoute]}>
          <App />
        </MemoryRouter>
      </AntdApp>
    </ConfigProvider>,
  )
}

describe('App shell preview baseline', () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue({
      user: {
        id: 1,
        name: '罗杰',
        email: 'admin@suying.ai',
        role: 'admin',
        tenantId: 'platform',
        tenantName: '平台运营',
        defaultTradeAccountId: 'paper-admin',
        tradeMode: 'paper',
        brokerAdapter: 'paper',
        permissions: [
          'dashboard', 'open_decision', 'screener', 'supply_chain_bom', 'predictions',
          'signals', 'trade', 'auto_trade', 'strategy', 'risk', 'backtest', 'diagnosis',
          'training', 'model_registry', 'data_update', 'runtime_status', 'p0_workflow',
          'platform_upgrade', 'admin_permissions', 'admin_memberships',
        ],
        membership: { status: 'inactive', isMember: false },
      },
      accessToken: 'token',
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
      hasRole: (...roles) => roles.includes('admin'),
      hasPermission: () => true,
    })
  })

  it('renders the optimized prototype shell without the removed platform explanation strip', async () => {
    renderShell('/')

    await waitFor(() => expect(screen.getByTestId('app-shell')).toBeInTheDocument())
    const navigation = screen.getByLabelText('主导航')
    expect(navigation).toBeInTheDocument()
    expect(screen.getByText('速赢')).toBeInTheDocument()
    expect(screen.getByText('AI')).toBeInTheDocument()

    const marketTape = screen.getByLabelText('市场行情')
    // 行情条为无缝滚动会复制多份（TAPE_COPIES），断言每份都渲染
    expect(within(marketTape).getAllByText('上证').length).toBeGreaterThan(0)
    expect(within(marketTape).getAllByText('深成').length).toBeGreaterThan(0)
    expect(within(marketTape).getAllByText('创业板').length).toBeGreaterThan(0)
    expect(within(marketTape).getAllByText('北证50').length).toBeGreaterThan(0)
    expect((await within(marketTape).findAllByText('4075.50')).length).toBeGreaterThan(0)
    expect(within(marketTape).getAllByText('+2.36%').length).toBeGreaterThan(0)

    expect(within(navigation).getByText('智能看板')).toBeInTheDocument()
    expect(within(navigation).getByText('开盘决策')).toBeInTheDocument()
    expect(within(navigation).getByText('智能选股')).toBeInTheDocument()
    expect(within(navigation).getByText('产业链拆解')).toBeInTheDocument()
    expect(within(navigation).queryByText('标签跟踪')).not.toBeInTheDocument()
    expect(within(navigation).getByText('交易中心')).toBeInTheDocument()
    expect(within(navigation).getByText('回测分析')).toBeInTheDocument()

    expect(screen.queryByText('公共+私有隔离')).not.toBeInTheDocument()
    expect(screen.queryByText('Cloud Ready')).not.toBeInTheDocument()
    expect(screen.queryByText('未绑定交易账户')).not.toBeInTheDocument()
  })

  it('uses precise header titles for nested trading routes', async () => {
    renderShell('/trade/risk-verdicts')

    await waitFor(() => expect(screen.getByTestId('app-shell')).toBeInTheDocument())
    const banner = screen.getByRole('banner')
    expect(within(banner).getByText('风控闸门')).toBeInTheDocument()
    expect(within(banner).queryByText(/^交易中心$/)).not.toBeInTheDocument()
  })

  it('uses the supply-chain UI prototype for legacy BOM URLs', async () => {
    renderShell('/supply-chain-bom/policy')

    await waitFor(() => expect(screen.getByTestId('app-shell')).toBeInTheDocument())
    expect(screen.getByText('产业链内容')).toBeInTheDocument()
    expect(within(screen.getByRole('banner')).getByText('产业链拆解')).toBeInTheDocument()
  })

  it('shows compact platform context in the header instead of page-body explainer cards', async () => {
    renderShell('/trade/order')

    await waitFor(() => expect(screen.getByTestId('app-shell')).toBeInTheDocument())
    const banner = screen.getByRole('banner')
    const platformContext = within(banner).getByLabelText('当前平台上下文')

    expect(within(platformContext).getByText('管理员视图')).toBeInTheDocument()
    expect(within(platformContext).getByText('paper-admin')).toBeInTheDocument()
    expect(within(platformContext).getByText('模拟盘')).toBeInTheDocument()
    expect(within(platformContext).getByText('非会员')).toBeInTheDocument()
    expect(screen.queryByText('角色视图')).not.toBeInTheDocument()
    expect(screen.queryByText('云端基线')).not.toBeInTheDocument()
  })
})
