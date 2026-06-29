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

  it('does not render the removed global platform explanation strip', () => {
    const { container } = renderBar({
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

    expect(container).toBeEmptyDOMElement()
    expect(screen.queryByText('操盘手')).not.toBeInTheDocument()
    expect(screen.queryByText('公共+私有隔离')).not.toBeInTheDocument()
    expect(screen.queryByText('Cloud Ready')).not.toBeInTheDocument()
  })
})
