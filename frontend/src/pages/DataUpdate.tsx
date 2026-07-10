import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { ClockCircleOutlined, DatabaseOutlined, ReloadOutlined, TableOutlined } from '@ant-design/icons'
import { signalApi } from '../api/client'
import type { DataStatusResponse, SyncSchedule } from '../api/types'
import {
  DataDomainBadge,
  DataFreshnessBar,
  MetricCard,
  PrototypeCard,
  PrototypePage,
  PrototypePageHeader,
  PrototypeTabs,
  RiskBanner,
  SegmentTabs,
  SideRail,
} from '../components/prototype'

const tabs = [
  { key: 'root', path: '/data-update', label: '数据更新', subLabel: '今日状态' },
  { key: 'overview', path: '/data-update/overview', label: '数据总览', subLabel: '质量 / 新鲜度' },
  { key: 'tables', path: '/data-update/tables', label: '全部数据表', subLabel: '表级质量' },
  { key: 'schedule', path: '/data-update/schedule', label: '同步调度', subLabel: '任务计划' },
]

const unavailableStatus: DataStatusResponse = {
  status: 'unavailable',
  total_tables: 0,
  active_tables: 0,
  total_rows: 0,
  sources: [],
  sync_map: {},
  fallback_reason: '数据状态接口不可用',
}

function activeTabFromPath(pathname: string) {
  if (pathname.includes('/overview')) return 'overview'
  if (pathname.includes('/tables')) return 'tables'
  if (pathname.includes('/schedule')) return 'schedule'
  return 'root'
}

function safeNumber(value: unknown, fallback: number) {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function normalizeDataStatus(input: Partial<DataStatusResponse> | undefined): DataStatusResponse {
  const value = input && typeof input === 'object' ? input : {}
  const normalizedStatus = value.status ?? unavailableStatus.status
  return {
    ...value,
    status: normalizedStatus,
    total_tables: safeNumber(value.total_tables, unavailableStatus.total_tables),
    active_tables: safeNumber(value.active_tables, unavailableStatus.active_tables),
    total_rows: safeNumber(value.total_rows, unavailableStatus.total_rows),
    sources: Array.isArray(value.sources)
      ? value.sources.map(source => ({
          ...source,
          rows: safeNumber(source.rows, 0),
          status: source.status || 'empty',
        }))
      : unavailableStatus.sources,
    sync_map: value.sync_map && typeof value.sync_map === 'object'
      ? value.sync_map
      : unavailableStatus.sync_map,
    fallback_reason: typeof value.fallback_reason === 'string' && value.fallback_reason.trim()
      ? value.fallback_reason
      : normalizedStatus === 'ok' ? undefined : unavailableStatus.fallback_reason,
  }
}

function formatRows(rows: number | undefined | null) {
  const safeRows = safeNumber(rows, 0)
  if (safeRows >= 10000) return `${Math.round(safeRows / 10000)}万`
  return safeRows.toLocaleString()
}

export default function DataUpdate() {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const active = activeTabFromPath(pathname)
  const [status, setStatus] = useState<DataStatusResponse>(unavailableStatus)
  const [schedules, setSchedules] = useState<SyncSchedule[]>([])
  const [filter, setFilter] = useState('all')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [syncingKey, setSyncingKey] = useState('')
  const [syncMessage, setSyncMessage] = useState('')

  const loadStatus = useCallback(async (cancelled?: () => boolean) => {
    setLoading(true)
    try {
      const [dataStatus, syncSchedules] = await Promise.all([
      signalApi.getDataStatus(),
      signalApi.getSyncSchedules(),
      ])
      if (cancelled?.()) return
      const normalizedStatus = normalizeDataStatus(dataStatus.data)
      setStatus(normalizedStatus)
      setSchedules(Array.isArray(syncSchedules.data?.schedules) ? syncSchedules.data.schedules : [])
      setError(normalizedStatus.status === 'ok'
        ? ''
        : normalizedStatus.fallback_reason || unavailableStatus.fallback_reason || '')
    } catch (err) {
      if (cancelled?.()) return
      const message = err instanceof Error
        ? err.message
        : typeof err === 'string' ? err : unavailableStatus.fallback_reason || '数据状态接口不可用'
      const reason = message.trim() || unavailableStatus.fallback_reason || '数据状态接口不可用'
      const normalizedMessage = reason.toLowerCase()
      if (normalizedMessage.includes('abort') || normalizedMessage.includes('cancel')) return
      setStatus({ ...unavailableStatus, fallback_reason: reason })
      setSchedules([])
      setError(reason)
    } finally {
      if (!cancelled?.()) setLoading(false)
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    loadStatus(() => cancelled)

    return () => {
      cancelled = true
    }
  }, [loadStatus])

  const runManualSync = async (tableKey: string, label: string) => {
    const days = status.sync_map[tableKey]?.days_default || 30
    setSyncingKey(tableKey)
    setSyncMessage('')
    try {
      const response = await signalApi.triggerSync(tableKey, days)
      if (response.data?.status === 'ok') {
        setSyncMessage(`${tableKey} 同步已触发：${label}`)
        await loadStatus()
      } else {
        setSyncMessage(`${tableKey} 同步失败：${response.data?.message || response.data?.stderr || '后端未返回原因'}`)
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : '请求失败'
      setSyncMessage(`${tableKey} 同步失败：${message}`)
    } finally {
      setSyncingKey('')
    }
  }

  const tab = useMemo(() => tabs.find(item => item.key === active) ?? tabs[0], [active])
  const statusUnavailable = status.status !== 'ok'
  const visibleSources = useMemo(() => {
    if (filter === 'all') return status.sources
    return status.sources.filter(source => source.status === filter || source.category === filter)
  }, [filter, status.sources])
  const normalSummary = statusUnavailable ? '数据状态未知' : `${status.active_tables}/${status.total_tables} 表正常`
  const latestSource = status.sources.find(source => source.key === 'daily_kline')
    ?? status.sources
      .filter(source => source.category === '行情' && source.max_date && source.max_date !== '-')
      .sort((a, b) => String(b.max_date).localeCompare(String(a.max_date)))[0]
  const latestSchedule = schedules.find(item => (item as SyncSchedule & { last_run_at?: string; last_run?: string }).last_run_at || (item as SyncSchedule & { last_run_at?: string; last_run?: string }).last_run) as (SyncSchedule & { last_run_at?: string; last_run?: string }) | undefined

  return (
    <PrototypePage>
      <PrototypeTabs
        items={tabs}
        activeKey={active}
        ariaLabel="数据更新模块页签"
        onChange={key => navigate(tabs.find(item => item.key === key)?.path ?? '/data-update')}
      />

      <PrototypePageHeader
        title={`数据更新 - ${tab.label}`}
        subtitle="同步总览 · 全表管理 · 调度计划 · 数据质量修复"
        dataFreshness={(
          <DataFreshnessBar
            tradeDate={latestSource?.max_date}
            updatedAt={latestSchedule?.last_run_at || latestSchedule?.last_run || latestSource?.max_date}
            source={latestSource ? `${latestSource.key}/${latestSource.source}` : 'signal/data-status'}
          />
        )}
        actions={[
          { key: 'public', label: '公共数据', active: true, tone: 'up' },
          { key: 'pg', label: 'PostgreSQL 优先', tone: 'neutral' },
        ]}
      />

      {error && <RiskBanner status="reject" title="数据状态不可用" detail={error} />}
      {syncMessage && <RiskBanner status={syncMessage.includes('失败') ? 'warn' : 'pass'} title="手动同步结果" detail={syncMessage} />}

      <div className="kpis">
        <MetricCard label="正常表" value={statusUnavailable ? '--' : status.active_tables} sub={normalSummary} tone="up" />
        <MetricCard label="总表数" value={statusUnavailable ? '--' : status.total_tables} sub="行情 / 基础 / 模型" tone="accent" />
        <MetricCard label="总行数" value={statusUnavailable ? '--' : formatRows(status.total_rows)} sub="当前可查询数据" tone="muted" />
        <MetricCard label="调度任务" value={statusUnavailable ? '--' : schedules.length || Object.keys(status.sync_map).length} sub="自动同步配置" tone="warn" />
      </div>

      <div className="r r-2-1">
        <PrototypeCard
          title={active === 'schedule' ? '同步调度' : active === 'tables' ? '全部数据表' : '数据质量总览'}
          icon={active === 'schedule' ? <ClockCircleOutlined /> : <DatabaseOutlined />}
          meta={<DataDomainBadge domain="public" label={statusUnavailable ? '状态未知' : '表状态正常'} />}
        >
          {active !== 'schedule' && (
            <>
              <SegmentTabs
                items={[
                  { key: 'all', label: '全部', count: status.total_tables },
                  { key: 'active', label: '正常', count: status.active_tables },
                  { key: 'empty', label: '待修复', count: status.total_tables - status.active_tables },
                ]}
                activeKey={filter}
                ariaLabel="数据表筛选"
                onChange={setFilter}
              />
              <table className="tbl" style={{ marginTop: 14 }}>
                <thead>
                  <tr>
                    <th>数据表</th>
                    <th>类别</th>
                    <th>来源</th>
                    <th>更新</th>
                    <th className="r">行数</th>
                    <th>日期范围</th>
                    <th>状态</th>
                    <th className="r">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleSources.map(source => (
                    <tr key={source.key}>
                      <td className="nm">{source.name}<div className="prototype-panel-note">{source.key}</div></td>
                      <td>{source.category}</td>
                      <td>{source.source}</td>
                      <td>{source.update}</td>
                      <td className="r">{formatRows(source.rows)}</td>
                      <td>{source.min_date} / {source.max_date}</td>
                      <td className={source.status === 'active' ? 'down' : 'up'}>{source.status === 'active' ? '正常' : '待修复'}</td>
                      <td className="r">
                        <button
                          type="button"
                          className="action-btn text"
                          onClick={() => runManualSync(source.key, source.name)}
                          disabled={!status.sync_map[source.key] || syncingKey === source.key}
                        >
                          {syncingKey === source.key ? '同步中...' : `同步${source.name}`}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}

          {active === 'schedule' && (
            <table className="tbl">
              <thead>
                <tr>
                  <th>表</th>
                  <th>模式</th>
                  <th>回补天数</th>
                  <th>启用</th>
                  <th>下次执行</th>
                </tr>
              </thead>
              <tbody>
                {(schedules.length > 0 ? schedules : Object.entries(status.sync_map).map(([key, item]) => ({
                  table_key: key,
                  days_back: item.days_default,
                  interval_minutes: item.mode === 'intra' ? 5 : 1440,
                  daily_at: item.mode === 'post_market' ? '17:20' : null,
                  enabled: true,
                  next_sync_at: item.mode,
                }))).map(schedule => (
                  <tr key={schedule.table_key}>
                    <td className="mono">{schedule.table_key}</td>
                    <td>{status.sync_map[schedule.table_key]?.mode || `${schedule.interval_minutes}m`}</td>
                    <td>{schedule.days_back}</td>
                    <td className={schedule.enabled ? 'down' : ''}>{schedule.enabled ? '启用' : '停用'}</td>
                    <td>{schedule.next_sync_at || schedule.daily_at || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </PrototypeCard>

        <SideRail title="数据质量" meta="Public">
          {!statusUnavailable && (
            <RiskBanner
              status={status.active_tables === status.total_tables ? 'pass' : 'warn'}
              title={status.active_tables === status.total_tables ? '所有表正常' : '部分表待修复'}
              detail="业务页面会携带数据时点与质量提示，私有方案不写入公共数据域。"
            />
          )}
          <PrototypeCard title="同步动作" icon={<ReloadOutlined />}>
            <div className="batch-actions" style={{ marginBottom: 12 }}>
              <button type="button" className="action-btn primary" onClick={() => loadStatus()} disabled={loading}>
                {loading ? '刷新中...' : '刷新状态'}
              </button>
              {latestSource && (
                <button
                  type="button"
                  className="action-btn"
                  onClick={() => runManualSync(latestSource.key, latestSource.name)}
                  disabled={!status.sync_map[latestSource.key] || syncingKey === latestSource.key}
                >
                  {syncingKey === latestSource.key ? '同步中...' : `同步${latestSource.name}`}
                </button>
              )}
            </div>
            <div className="li-row">
              <div className="li-badge">D</div>
              <div className="li-main">
                <div className="n">盘后日线同步</div>
                <div className="s">默认回补 30 天，失败后进入修复队列</div>
              </div>
            </div>
            <div className="li-row">
              <div className="li-badge">Q</div>
              <div className="li-main">
                <div className="n">质量检查</div>
                <div className="s">空表、日期断档、行数异常自动标红</div>
              </div>
            </div>
          </PrototypeCard>
          <PrototypeCard title="表域边界" icon={<TableOutlined />}>
            <div className="prototype-panel-note">行情、基础数据、模型产物属于公共域；自选、方案、订单、风控判定属于私有域。</div>
          </PrototypeCard>
        </SideRail>
      </div>
    </PrototypePage>
  )
}
