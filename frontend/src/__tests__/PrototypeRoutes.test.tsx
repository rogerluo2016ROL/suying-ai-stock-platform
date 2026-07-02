import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ConfigProvider, App as AntdApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { MemoryRouter } from 'react-router-dom'
import type { AuthContextValue } from '../contexts/AuthContext'
import App from '../App'

const mockUseAuth = vi.fn<() => AuthContextValue>()
const liveTradeApiMock = vi.hoisted(() => ({
  getBrokerStatus: vi.fn(),
}))

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
    getUnreadCount: vi.fn().mockResolvedValue({ data: { unread: 0 } }),
  },
  // App.tsx refreshMarketTape 调 marketApi.getIndexQuotes()（9f02b734 引入），
  // mock 需提供，否则 App shell mount 时 marketApi 为 undefined → 70 route 用例全挂
  marketApi: {
    getIndexQuotes: vi.fn().mockResolvedValue({ data: { data: { diff: [] } } }),
  },
  clearPlatformContext: vi.fn(),
  injectPlatformContext: vi.fn(),
}))

vi.mock('../api/liveTrade', () => ({
  liveTradeApi: liveTradeApiMock,
}))

vi.mock('../pages/Dashboard', () => ({ default: () => <div>Dashboard page</div> }))
vi.mock('../pages/OpenDecision', () => ({ default: () => <div>OpenDecision page</div> }))
vi.mock('../pages/Screener', () => ({ default: () => <div>Screener page</div> }))
vi.mock('../pages/SupplyChainBom', () => ({ default: () => <div>SupplyChain page</div> }))
vi.mock('../pages/Predictions', () => ({ default: () => <div>Predictions page</div> }))
vi.mock('../pages/Signals', () => ({ default: () => <div>Signals page</div> }))
vi.mock('../pages/Trade', () => ({ default: () => <div>Trade page</div> }))
vi.mock('../pages/AuditLog', () => ({ default: () => <div>Audit page</div> }))
vi.mock('../pages/RiskVerdicts', () => ({ default: () => <div>RiskVerdicts page</div> }))
vi.mock('../pages/DecisionContexts', () => ({ default: () => <div>DecisionContexts page</div> }))
vi.mock('../pages/Diagnosis', () => ({ default: () => <div>Diagnosis page</div> }))
vi.mock('../pages/Backtest', () => ({ default: () => <div>Backtest page</div> }))
vi.mock('../pages/Strategy', () => ({ default: () => <div>Strategy page</div> }))
vi.mock('../pages/AutoTrade', () => ({ default: () => <div>AutoTrade page</div> }))
vi.mock('../pages/RiskControl', () => ({ default: () => <div>RiskControl page</div> }))
vi.mock('../pages/Training', () => ({ default: () => <div>Training page</div> }))
vi.mock('../pages/ModelRegistry', () => ({ default: () => <div>ModelRegistry page</div> }))
vi.mock('../pages/DataUpdate', () => ({ default: () => <div>DataUpdate page</div> }))
vi.mock('../pages/RuntimeStatus', () => ({ default: () => <div>RuntimeStatus page</div> }))
vi.mock('../pages/P0Workflow', () => ({ default: () => <div>P0Workflow page</div> }))
vi.mock('../pages/PlatformUpgrade', () => ({ default: () => <div>PlatformUpgrade page</div> }))
vi.mock('../pages/AdminPermissions', () => ({ default: () => <div>AdminPermissions page</div> }))
vi.mock('../pages/MembershipManagement', () => ({ default: () => <div>MembershipManagement page</div> }))

const routes = [
  '/', '/dashboard/auction', '/dashboard/signals', '/dashboard/watchlist',
  '/open-decision', '/open-decision/auction', '/open-decision/signals', '/open-decision/candidates', '/open-decision/execution',
  '/screener', '/screener/models', '/screener/factors',
  '/supply-chain-bom', '/supply-chain-bom/policy', '/supply-chain-bom/company',
  '/predictions', '/predictions/single', '/predictions/compare', '/predictions/backtest',
  '/signals', '/signals/overview', '/signals/history', '/signals/risk',
  '/trade', '/trade/order', '/trade/positions', '/trade/orders', '/trade/account', '/trade/brokers',
  '/trade/audit-log', '/trade/risk-verdicts', '/trade/decision-contexts',
  '/auto-trade', '/auto-trade/config', '/auto-trade/monitor', '/auto-trade/logs',
  '/strategy', '/strategy/detail', '/strategy/compare', '/strategy/reports',
  '/risk', '/risk/overview', '/risk/positions', '/risk/strategies', '/risk/market', '/risk/audit',
  '/backtest', '/backtest/run', '/backtest/compare', '/backtest/trades',
  '/diagnosis', '/diagnosis/overview', '/diagnosis/model', '/diagnosis/compare', '/diagnosis/risk',
  '/training', '/training/tasks', '/training/mlflow',
  '/model-registry',
  '/data-update', '/data-update/overview', '/data-update/tables', '/data-update/schedule',
  '/runtime', '/runtime-status', '/workflow/p0', '/platform/upgrade',
  '/admin/permissions', '/admin/memberships',
]

const adminPermissions = [
  'dashboard', 'open_decision', 'screener', 'supply_chain_bom', 'predictions',
  'signals', 'trade', 'auto_trade', 'strategy', 'risk', 'backtest', 'diagnosis',
  'training', 'model_registry', 'data_update', 'runtime_status', 'p0_workflow',
  'platform_upgrade', 'admin_permissions', 'admin_memberships',
]

const pageSources = import.meta.glob('../pages/*.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

function renderRoute(initialRoute: string) {
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

describe('prototype route coverage', () => {
  beforeEach(() => {
    liveTradeApiMock.getBrokerStatus.mockReset()
    liveTradeApiMock.getBrokerStatus.mockResolvedValue({
      data: { status: 'disconnected', broker_name: 'paper', account_id: 'paper-admin' },
    })
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
        permissions: adminPermissions,
        membership: { status: 'inactive', isMember: false },
      },
      accessToken: 'token',
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
      hasRole: (...roles) => roles.includes('admin'),
      hasPermission: (permission) => adminPermissions.includes(permission),
    })
  })

  it.each(routes)('renders prototype route %s inside the app shell', async (route) => {
    renderRoute(route)

    await waitFor(() => expect(screen.getByTestId('app-shell')).toBeInTheDocument())
    expect(screen.queryByText('登录')).not.toBeInTheDocument()
  })

  it('covers every preview route from the Phase 0 matrix plus existing trade integration routes', () => {
    expect(routes).toHaveLength(69)
  })

  it('does not route production pages through the generic NewUiModulePage fallback', () => {
    const offenders = Object.entries(pageSources)
      .filter(([file]) => !file.endsWith('/NewUiModulePage.tsx'))
      .filter(([, source]) => source.includes('NewUiModulePage'))
      .map(([file]) => file.split('/').pop())

    expect(offenders).toEqual([])
  })

  it('shows live broker connection status in the global header', async () => {
    liveTradeApiMock.getBrokerStatus.mockResolvedValue({
      data: {
        status: 'connected',
        broker_name: 'xtquant_qmt',
        account_id: 'qmt-880001',
      },
    })
    mockUseAuth.mockReturnValue({
      user: {
        id: 1,
        name: '罗杰',
        email: 'admin@suying.ai',
        role: 'admin',
        tenantId: 'platform',
        tenantName: '平台运营',
        defaultTradeAccountId: 'qmt-880001',
        tradeMode: 'live',
        brokerAdapter: 'xtquant_qmt',
        permissions: adminPermissions,
        membership: { status: 'inactive', isMember: false },
      },
      accessToken: 'token',
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
      hasRole: (...roles) => roles.includes('admin'),
      hasPermission: (permission) => adminPermissions.includes(permission),
    })

    renderRoute('/trade')

    const platformContext = await screen.findByLabelText('当前平台上下文')
    fireEvent.click(platformContext)
    await waitFor(() => expect(screen.getByText(/券商：券商已连接 · qmt-880001/)).toBeInTheDocument())
  })
})
