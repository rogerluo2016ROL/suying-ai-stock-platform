import { render, screen } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { PlatformContextBar } from '../components/layout'
import { buildPlatformSessionFromUser, roleToRoleView } from '../types/platform'
import type { User } from '../contexts/AuthContext'

function renderBar(user: User | null) {
  return render(
    <ConfigProvider locale={zhCN}>
      <PlatformContextBar session={buildPlatformSessionFromUser(user)} />
    </ConfigProvider>,
  )
}

describe('PlatformContextBar', () => {
  it('maps existing RBAC roles to the new platform role views', () => {
    expect(roleToRoleView('admin')).toBe('admin')
    expect(roleToRoleView('internal_analyst')).toBe('trader')
    expect(roleToRoleView('external_analyst')).toBe('trader')
    expect(roleToRoleView('user')).toBe('investor')
  })

  it('renders deterministic platform defaults for an admin user', () => {
    renderBar({
      id: 1,
      name: '罗杰',
      email: 'admin@suying.ai',
      role: 'admin',
    })

    expect(screen.getByText('系统管理员')).toBeInTheDocument()
    expect(screen.getByText('平台运营')).toBeInTheDocument()
    expect(screen.getByText('platform')).toBeInTheDocument()
    expect(screen.getByText('未绑定交易账户')).toBeInTheDocument()
    expect(screen.getByText('公共+私有隔离')).toBeInTheDocument()
    expect(screen.getByText('模拟盘')).toBeInTheDocument()
    expect(screen.getByText('paper')).toBeInTheDocument()
  })

  it('renders tenant, account, live mode and broker adapter when backend supplies platform fields', () => {
    renderBar({
      id: 8,
      name: '操盘手A',
      email: 'trader@suying.ai',
      role: 'internal_analyst',
      tenantId: 'tenant-alpha',
      tenantName: 'Alpha 量化组',
      defaultTradeAccountId: 'acct-qmt-01',
      tradeMode: 'live',
      brokerAdapter: 'xtquant_qmt',
    })

    expect(screen.getByText('操盘手')).toBeInTheDocument()
    expect(screen.getByText('Alpha 量化组')).toBeInTheDocument()
    expect(screen.getByText('tenant-alpha')).toBeInTheDocument()
    expect(screen.getByText('acct-qmt-01')).toBeInTheDocument()
    expect(screen.getByText('实盘')).toBeInTheDocument()
    expect(screen.getByText('xtquant_qmt')).toBeInTheDocument()
  })
})
