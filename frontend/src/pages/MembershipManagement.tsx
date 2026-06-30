import { useEffect, useMemo, useState } from 'react'
import { Button, Input, Select, Tag, message } from 'antd'
import {
  CheckCircleOutlined,
  CrownOutlined,
  ReloadOutlined,
  StopOutlined,
} from '@ant-design/icons'
import { adminApi, type MembershipUser } from '../api/client'

const STATUS_OPTIONS = [
  { value: '', label: '全部状态' },
  { value: 'inactive', label: '未开通' },
  { value: 'trial', label: '试用' },
  { value: 'active', label: '会员中' },
  { value: 'expired', label: '已到期' },
  { value: 'cancelled', label: '已停用' },
]

function statusLabel(status: string): string {
  return STATUS_OPTIONS.find(item => item.value === status)?.label || status
}

function statusTone(status: string): 'success' | 'warning' | 'error' | 'default' {
  if (status === 'active' || status === 'trial') return 'success'
  if (status === 'expired') return 'warning'
  if (status === 'cancelled') return 'error'
  return 'default'
}

function formatDate(value?: string | null): string {
  return value ? value.slice(0, 10) : '-'
}

function chinaIsoDateTime(date: Date, endOfDay = false): string {
  const local = new Date(date.getTime() + 8 * 60 * 60 * 1000)
  const day = local.toISOString().slice(0, 10)
  return `${day}T${endOfDay ? '23:59:59' : '00:00:00'}+08:00`
}

function addDays(date: Date, days: number): Date {
  const next = new Date(date)
  next.setDate(next.getDate() + days)
  return next
}

export default function MembershipManagement() {
  const [members, setMembers] = useState<MembershipUser[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('')
  const [busyUserId, setBusyUserId] = useState<number | null>(null)

  const stats = useMemo(() => {
    const active = members.filter(item => item.membership.is_member).length
    const expiring = members.filter(item => {
      const days = item.membership.days_remaining
      return item.membership.is_member && typeof days === 'number' && days <= 7
    }).length
    const expired = members.filter(item => item.membership.status === 'expired').length
    return { active, expiring, expired }
  }, [members])

  const loadData = async () => {
    setLoading(true)
    try {
      const resp = await adminApi.getMemberships({
        page_size: 100,
        q: query || undefined,
        status: status || undefined,
      })
      setMembers(resp.data.members)
      setTotal(resp.data.total)
    } catch {
      message.error('加载会员数据失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const updateMembership = async (member: MembershipUser, action: 'activate' | 'cancel') => {
    setBusyUserId(member.id)
    try {
      const now = new Date()
      const payload = action === 'activate'
        ? {
            membership: {
              status: 'active',
              plan: member.membership.plan || 'pro',
              starts_at: chinaIsoDateTime(now),
              ends_at: chinaIsoDateTime(addDays(now, 30), true),
              source: 'admin',
              note: '会员管理页快速开通 30 天',
            },
          }
        : {
            membership: {
              status: 'cancelled',
              plan: member.membership.plan || null,
              starts_at: member.membership.starts_at || null,
              ends_at: member.membership.ends_at || null,
              source: 'admin',
              note: '会员管理页停用',
            },
          }
      const resp = await adminApi.updateUserAuthorization(member.id, payload)
      setMembers(prev => prev.map(item => (
        item.id === member.id
          ? {
              ...item,
              role: resp.data.role,
              is_active: resp.data.is_active,
              membership: resp.data.membership || item.membership,
            }
          : item
      )))
      message.success(action === 'activate' ? '已开通 30 天会员' : '已停用会员')
    } catch {
      message.error(action === 'activate' ? '开通会员失败' : '停用会员失败')
    } finally {
      setBusyUserId(null)
    }
  }

  return (
    <div className="admin-page">
      <div className="page-head">
        <div>
          <h1>会员管理</h1>
          <div className="sub">会员状态、套餐、起止周期和临期风险</div>
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
          <Select
            value={status}
            options={STATUS_OPTIONS}
            onChange={setStatus}
            style={{ width: 130 }}
          />
          <Button icon={<ReloadOutlined />} loading={loading} onClick={loadData}>
            刷新
          </Button>
        </div>
      </div>

      <div className="kpis admin-kpis">
        <div className="kpi">
          <div className="k-top"><span className="k-lbl">列表用户</span><span className="k-ic"><CrownOutlined /></span></div>
          <div className="k-val">{total}</div>
          <div className="k-sub">当前筛选结果</div>
        </div>
        <div className="kpi">
          <div className="k-top"><span className="k-lbl">有效会员</span><span className="k-ic"><CheckCircleOutlined /></span></div>
          <div className="k-val">{stats.active}</div>
          <div className="k-sub">状态有效且未过期</div>
        </div>
        <div className="kpi">
          <div className="k-top"><span className="k-lbl">7天内到期</span><span className="k-ic"><ReloadOutlined /></span></div>
          <div className="k-val">{stats.expiring}</div>
          <div className="k-sub">需要续期跟进</div>
        </div>
        <div className="kpi">
          <div className="k-top"><span className="k-lbl">已过期</span><span className="k-ic"><StopOutlined /></span></div>
          <div className="k-val">{stats.expired}</div>
          <div className="k-sub">不能再按会员权益使用</div>
        </div>
      </div>

      <section className="card admin-card mt14">
        <div className="card-h">
          <span className="ic"><CrownOutlined /></span>
          <h3>会员列表</h3>
          <span className="meta">购买状态与周期</span>
        </div>
        <div className="card-b admin-table-wrap">
          <table className="tbl admin-table">
            <thead>
              <tr>
                <th>用户</th>
                <th>角色</th>
                <th>状态</th>
                <th>套餐</th>
                <th>开始</th>
                <th>到期</th>
                <th className="r">剩余天数</th>
                <th className="r">操作</th>
              </tr>
            </thead>
            <tbody>
              {members.map(item => (
                <tr key={item.id}>
                  <td>
                    <div className="admin-user-cell">
                      <b>{item.name}</b>
                      <small>{item.email}</small>
                    </div>
                  </td>
                  <td>{item.role}</td>
                  <td>
                    <Tag color={statusTone(item.membership.status)}>
                      {statusLabel(item.membership.status)}
                    </Tag>
                  </td>
                  <td>{item.membership.plan || '-'}</td>
                  <td>{formatDate(item.membership.starts_at)}</td>
                  <td>{formatDate(item.membership.ends_at)}</td>
                  <td className="r">
                    {typeof item.membership.days_remaining === 'number'
                      ? item.membership.days_remaining
                      : '-'}
                  </td>
                  <td className="r">
                    <div className="admin-actions">
                      <Button
                        size="small"
                        icon={<CheckCircleOutlined />}
                        loading={busyUserId === item.id}
                        onClick={() => updateMembership(item, 'activate')}
                      >
                        开通30天
                      </Button>
                      <Button
                        size="small"
                        danger
                        icon={<StopOutlined />}
                        loading={busyUserId === item.id}
                        onClick={() => updateMembership(item, 'cancel')}
                      >
                        停用
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
              {members.length === 0 && (
                <tr>
                  <td colSpan={8}><div className="empty">没有匹配会员记录</div></td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
