import { useEffect, useMemo, useState } from 'react'
import { Button, Checkbox, Input, Select, Switch, Tag, message } from 'antd'
import {
  CrownOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SaveOutlined,
} from '@ant-design/icons'
import {
  adminApi,
  type AdminUser,
  type PermissionItem,
  type RolePermissions,
} from '../api/client'

const ROLE_OPTIONS = [
  { value: 'admin', label: '平台管理员' },
  { value: 'internal_analyst', label: '操盘手' },
  { value: 'external_analyst', label: '外部分析师' },
  { value: 'user', label: '个人投资者' },
]

const MEMBERSHIP_STATUS_OPTIONS = [
  { value: 'inactive', label: '未开通' },
  { value: 'trial', label: '试用' },
  { value: 'active', label: '会员中' },
  { value: 'expired', label: '已到期' },
  { value: 'cancelled', label: '已停用' },
]

function roleLabel(role: string): string {
  return ROLE_OPTIONS.find(item => item.value === role)?.label || role
}

function statusTone(status?: string): 'success' | 'warning' | 'error' | 'default' {
  if (status === 'active' || status === 'trial') return 'success'
  if (status === 'expired') return 'warning'
  if (status === 'cancelled') return 'error'
  return 'default'
}

function toDateInput(value?: string | null): string {
  return value ? value.slice(0, 10) : ''
}

function toApiDateTime(value: string, endOfDay = false): string | null {
  if (!value) return null
  return `${value}T${endOfDay ? '23:59:59' : '00:00:00'}+08:00`
}

function groupPermissions(items: PermissionItem[]): Record<string, PermissionItem[]> {
  return items.reduce<Record<string, PermissionItem[]>>((acc, item) => {
    acc[item.group] = acc[item.group] || []
    acc[item.group].push(item)
    return acc
  }, {})
}

export default function AdminPermissions() {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [roles, setRoles] = useState<RolePermissions[]>([])
  const [loading, setLoading] = useState(false)
  const [savingUser, setSavingUser] = useState(false)
  const [savingRole, setSavingRole] = useState(false)
  const [query, setQuery] = useState('')
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null)
  const [selectedRoleName, setSelectedRoleName] = useState('user')
  const [draftPermissionKeys, setDraftPermissionKeys] = useState<string[]>([])

  const [draftRole, setDraftRole] = useState('user')
  const [draftActive, setDraftActive] = useState(true)
  const [draftMembershipStatus, setDraftMembershipStatus] = useState('inactive')
  const [draftPlan, setDraftPlan] = useState('')
  const [draftStartsAt, setDraftStartsAt] = useState('')
  const [draftEndsAt, setDraftEndsAt] = useState('')
  const [draftNote, setDraftNote] = useState('')

  const selectedUser = users.find(item => item.id === selectedUserId) || null
  const selectedRole = roles.find(item => item.role === selectedRoleName) || roles[0] || null
  const selectedRoleEnabledCount = selectedRole
    ? selectedRole.permissions.filter(item => item.enabled).length
    : 0
  const activeMemberCount = users.filter(item => item.membership?.is_member).length

  const groupedPermissions = useMemo(
    () => groupPermissions(selectedRole?.permissions || []),
    [selectedRole],
  )

  const loadData = async () => {
    setLoading(true)
    try {
      const [usersRes, rolesRes] = await Promise.all([
        adminApi.getUsers({ page_size: 100, q: query || undefined }),
        adminApi.getRolePermissions(),
      ])
      setUsers(usersRes.data.users)
      setRoles(rolesRes.data.roles)
      if (!selectedUserId && usersRes.data.users.length > 0) {
        setSelectedUserId(usersRes.data.users[0].id)
      }
      if (!rolesRes.data.roles.find(item => item.role === selectedRoleName)) {
        setSelectedRoleName(rolesRes.data.roles[0]?.role || 'user')
      }
    } catch {
      message.error('加载权限数据失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!selectedUser) return
    setDraftRole(selectedUser.role)
    setDraftActive(selectedUser.is_active)
    setDraftMembershipStatus(selectedUser.membership?.status || 'inactive')
    setDraftPlan(selectedUser.membership?.plan || '')
    setDraftStartsAt(toDateInput(selectedUser.membership?.starts_at))
    setDraftEndsAt(toDateInput(selectedUser.membership?.ends_at))
    setDraftNote(selectedUser.membership?.note || '')
  }, [selectedUser])

  useEffect(() => {
    if (!selectedRole) return
    setDraftPermissionKeys(
      selectedRole.permissions
        .filter(item => item.enabled)
        .map(item => item.key),
    )
  }, [selectedRole])

  const saveUserAuthorization = async () => {
    if (!selectedUser) return
    setSavingUser(true)
    try {
      const resp = await adminApi.updateUserAuthorization(selectedUser.id, {
        role: draftRole,
        is_active: draftActive,
        membership: {
          status: draftMembershipStatus,
          plan: draftPlan || null,
          starts_at: toApiDateTime(draftStartsAt),
          ends_at: toApiDateTime(draftEndsAt, true),
          source: 'admin',
          note: draftNote || null,
        },
      })
      setUsers(prev => prev.map(item => item.id === selectedUser.id ? resp.data : item))
      message.success('用户授权已更新')
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
      message.error(detail || '保存用户授权失败')
    } finally {
      setSavingUser(false)
    }
  }

  const togglePermission = (key: string, checked: boolean) => {
    setDraftPermissionKeys(prev => {
      const next = new Set(prev)
      if (checked) next.add(key)
      else next.delete(key)
      return Array.from(next)
    })
  }

  const saveRolePermissions = async () => {
    if (!selectedRole) return
    setSavingRole(true)
    try {
      const resp = await adminApi.updateRolePermissions(selectedRole.role, draftPermissionKeys)
      setRoles(prev => prev.map(item => item.role === resp.data.role ? resp.data : item))
      message.success('角色菜单权限已更新')
    } catch {
      message.error('保存角色权限失败')
    } finally {
      setSavingRole(false)
    }
  }

  return (
    <div className="admin-page">
      <div className="page-head">
        <div>
          <h1>权限授权</h1>
          <div className="sub">用户角色、账号状态、会员周期和角色菜单权限</div>
        </div>
        <div className="head-actions">
          <Input.Search
            allowClear
            placeholder="搜索用户或邮箱"
            value={query}
            onChange={event => setQuery(event.target.value)}
            onSearch={loadData}
            style={{ width: 220 }}
          />
          <Button icon={<ReloadOutlined />} loading={loading} onClick={loadData}>
            刷新
          </Button>
        </div>
      </div>

      <div className="kpis admin-kpis">
        <div className="kpi">
          <div className="k-top"><span className="k-lbl">用户数</span><span className="k-ic"><SafetyCertificateOutlined /></span></div>
          <div className="k-val">{users.length}</div>
          <div className="k-sub">当前筛选范围</div>
        </div>
        <div className="kpi">
          <div className="k-top"><span className="k-lbl">有效会员</span><span className="k-ic"><CrownOutlined /></span></div>
          <div className="k-val">{activeMemberCount}</div>
          <div className="k-sub">状态与周期共同判定</div>
        </div>
        <div className="kpi">
          <div className="k-top"><span className="k-lbl">角色权限</span><span className="k-ic"><SafetyCertificateOutlined /></span></div>
          <div className="k-val">{roles.length}</div>
          <div className="k-sub">内置角色可编辑菜单</div>
        </div>
        <div className="kpi">
          <div className="k-top"><span className="k-lbl">当前角色开启</span><span className="k-ic"><SaveOutlined /></span></div>
          <div className="k-val">{selectedRoleEnabledCount}</div>
          <div className="k-sub">{selectedRole?.label || '-'}</div>
        </div>
      </div>

      <div className="grid r-1-1 mt14">
        <section className="card admin-card">
          <div className="card-h">
            <span className="ic"><SafetyCertificateOutlined /></span>
            <h3>用户授权</h3>
            <span className="meta">选择用户后修改授权</span>
          </div>
          <div className="card-b admin-split">
            <div className="admin-user-list">
              {users.map(item => (
                <button
                  key={item.id}
                  type="button"
                  className={`admin-user-row${selectedUserId === item.id ? ' active' : ''}`}
                  onClick={() => setSelectedUserId(item.id)}
                >
                  <span>
                    <b>{item.name}</b>
                    <small>{item.email} · {roleLabel(item.role)}</small>
                  </span>
                  <Tag color={statusTone(item.membership?.status)}>
                    {item.membership?.is_member ? '会员' : '非会员'}
                  </Tag>
                </button>
              ))}
              {users.length === 0 && <div className="empty">没有匹配用户</div>}
            </div>

            <div className="admin-form">
              <div className="field">
                <label>授权角色</label>
                <Select
                  value={draftRole}
                  options={ROLE_OPTIONS}
                  onChange={setDraftRole}
                  style={{ width: '100%' }}
                />
              </div>
              <div className="field admin-switch-line">
                <label>账号状态</label>
                <Switch checked={draftActive} onChange={setDraftActive} checkedChildren="启用" unCheckedChildren="停用" />
              </div>
              <div className="field">
                <label>会员状态</label>
                <Select
                  value={draftMembershipStatus}
                  options={MEMBERSHIP_STATUS_OPTIONS}
                  onChange={setDraftMembershipStatus}
                  style={{ width: '100%' }}
                />
              </div>
              <div className="field">
                <label>会员套餐</label>
                <Input value={draftPlan} onChange={event => setDraftPlan(event.target.value)} placeholder="basic / pro / vip" />
              </div>
              <div className="admin-date-row">
                <div className="field">
                  <label>开始日期</label>
                  <input className="inp" type="date" value={draftStartsAt} onChange={event => setDraftStartsAt(event.target.value)} />
                </div>
                <div className="field">
                  <label>到期日期</label>
                  <input className="inp" type="date" value={draftEndsAt} onChange={event => setDraftEndsAt(event.target.value)} />
                </div>
              </div>
              <div className="field">
                <label>备注</label>
                <Input.TextArea rows={3} value={draftNote} onChange={event => setDraftNote(event.target.value)} />
              </div>
              <Button
                type="primary"
                icon={<SaveOutlined />}
                loading={savingUser}
                disabled={!selectedUser}
                onClick={saveUserAuthorization}
              >
                保存用户授权
              </Button>
            </div>
          </div>
        </section>

        <section className="card admin-card">
          <div className="card-h">
            <span className="ic"><SafetyCertificateOutlined /></span>
            <h3>角色菜单权限</h3>
            <span className="meta">默认权限可调整</span>
          </div>
          <div className="card-b">
            <div className="admin-role-toolbar">
              <Select
                value={selectedRoleName}
                options={roles.map(item => ({ value: item.role, label: `${item.label} · ${item.role}` }))}
                onChange={setSelectedRoleName}
                style={{ minWidth: 220 }}
              />
              <Button
                type="primary"
                icon={<SaveOutlined />}
                loading={savingRole}
                disabled={!selectedRole}
                onClick={saveRolePermissions}
              >
                保存角色权限
              </Button>
            </div>

            <div className="permission-matrix">
              {Object.entries(groupedPermissions).map(([group, items]) => (
                <div className="permission-group" key={group}>
                  <div className="permission-group-title">{group}</div>
                  {items.map(item => (
                    <label className="permission-row" key={item.key}>
                      <Checkbox
                        checked={draftPermissionKeys.includes(item.key)}
                        onChange={event => togglePermission(item.key, event.target.checked)}
                      />
                      <span>
                        <b>{item.label}</b>
                        <small>{item.description}</small>
                      </span>
                    </label>
                  ))}
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
