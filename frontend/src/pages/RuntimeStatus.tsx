import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiOutlined, CheckCircleOutlined, ClockCircleOutlined, DatabaseOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { healthApi } from '../api/client'
import { DataDomainBadge, DataFreshnessBar, MetricCard, PrototypeCard, PrototypePage, PrototypePageHeader, RiskBanner, SideRail } from '../components/prototype'

interface RuntimeServiceConfig {
  key: string
  name: string
  port: string
  duty: string
  enabled?: boolean
}

const serviceChecks: RuntimeServiceConfig[] = [
  { key: 'gateway', name: 'api-gateway', port: '18080', duty: '统一入口 / 鉴权透传' },
  { key: 'auth', name: 'backend-auth', port: '19001', duty: 'JWT / RBAC / tenant' },
  { key: 'prediction', name: 'prediction-service', port: '18002', duty: 'Kronos 预测' },
  { key: 'strategy', name: 'strategy-service', port: '18003', duty: '方案 / 自动策略' },
  { key: 'signal', name: 'signal-service', port: '18004', duty: '交易信号' },
  { key: 'trade', name: 'trade-service', port: '18006', duty: '模拟盘交易' },
  { key: 'backtest', name: 'backtest-service', port: '18007', duty: '回测复盘' },
  { key: 'training', name: 'training-service', port: '18008', duty: '训练队列' },
  { key: 'diagnosis', name: 'diagnosis-service', port: '18009', duty: '个股诊断' },
]

interface RuntimeServiceRow extends RuntimeServiceConfig {
  status: string
  version?: string
}

function isHealthy(status: string) {
  return ['healthy', 'online', 'ok'].includes(status)
}

function isEnabled(service: RuntimeServiceRow) {
  return service.enabled !== false
}

export default function RuntimeStatus() {
  const [services, setServices] = useState<RuntimeServiceRow[]>(
    serviceChecks.map(service => ({ ...service, status: 'checking' })),
  )
  const [lastCheckedAt, setLastCheckedAt] = useState('')

  const loadServices = useCallback(async () => {
    setServices(serviceChecks.map(service => ({ ...service, status: 'checking' })))
    try {
      const runtime = await healthApi.runtimeReadiness()
      const states = runtime.data?.services || {}
      setServices(serviceChecks.map(service => ({ ...service, status: states[service.name]?.ready ? 'healthy' : 'offline' })))
      setLastCheckedAt(new Date().toISOString())
      return
    } catch {
      // fall back to legacy per-service checks while older gateways roll out
    }
    const rows = await Promise.all(serviceChecks.map(async service => {
      if (service.enabled === false) {
        return { ...service, status: '未启用' }
      }
      try {
        const response = service.key === 'gateway'
          ? await healthApi.gateway()
          : await healthApi.check(service.key)
        return {
          ...service,
          status: String(response.data?.status || 'unknown'),
          version: response.data?.version,
        }
      } catch {
        return { ...service, status: 'offline' }
      }
    }))
    setServices(rows)
    setLastCheckedAt(new Date().toISOString())
  }, [])

  useEffect(() => {
    let mounted = true
    loadServices().finally(() => {
      if (!mounted) return
    })
    return () => {
      mounted = false
    }
  }, [loadServices])

  const summary = useMemo(() => {
    const activeServices = services.filter(isEnabled)
    const online = activeServices.filter(service => isHealthy(service.status)).length
    const checking = activeServices.filter(service => service.status === 'checking').length
    const offline = activeServices.length - online - checking
    return { online, checking, offline, total: activeServices.length }
  }, [services])

  const serviceStatus = useMemo(() => {
    return Object.fromEntries(services.map(service => [service.key, service.status])) as Record<string, string>
  }, [services])

  const trainingEnabled = services.find(service => service.key === 'training')?.enabled !== false
  const modelHealthy = isHealthy(serviceStatus.prediction || '') && (
    !trainingEnabled || isHealthy(serviceStatus.training || '')
  )
  const tradeHealthy = isHealthy(serviceStatus.trade || '')

  return (
    <PrototypePage>
      <PrototypePageHeader
        title="运行状态 - 服务健康"
        subtitle="服务健康 · 数据延迟 · 模型任务 · 交易链路"
        dataFreshness={<DataFreshnessBar tradeDate={lastCheckedAt} updatedAt={lastCheckedAt} source="health-api" currentTradeDate={lastCheckedAt} />}
        actions={[
          { key: 'admin', label: '管理员视图', active: true, tone: 'neutral' },
          { key: 'refresh', label: '刷新健康', tone: 'neutral', onClick: () => void loadServices() },
          { key: 'paper', label: '实盘默认关闭', tone: 'warn' },
        ]}
      />
      <div className="kpis">
        <MetricCard label="在线服务" value={`${summary.online}/${summary.total}`} sub={`异常 ${summary.offline}`} tone={summary.offline ? 'warn' : 'up'} />
        <MetricCard label="检查中" value={String(summary.checking)} sub="服务健康" tone="accent" />
        <MetricCard label="模型服务" value={modelHealthy ? 'OK' : '异常'} sub={trainingEnabled ? 'prediction + training' : 'prediction'} tone={modelHealthy ? 'up' : 'warn'} />
        <MetricCard label="交易链路" value={tradeHealthy ? 'Paper' : '异常'} sub="trade health" tone={tradeHealthy ? 'muted' : 'warn'} />
      </div>
      <div className="r r-2-1">
        <PrototypeCard
          title="服务健康矩阵"
          icon={<ApiOutlined />}
          meta={<DataDomainBadge domain="public" label="runtime-admin" />}
        >
          <table className="tbl">
            <thead>
              <tr>
                <th>服务</th>
                <th>端口</th>
                <th>状态</th>
                <th>职责</th>
              </tr>
            </thead>
            <tbody>
              {services.map(service => (
                <tr key={service.key}>
                  <td className="nm">{service.name}</td>
                  <td className="mono">{service.port}</td>
                  <td>
                    {isHealthy(service.status)
                      ? <CheckCircleOutlined className="up" />
                      : <ClockCircleOutlined style={{ color: 'var(--warn)' }} />} {service.status}
                  </td>
                  <td>{service.duty}{service.version ? ` / ${service.version}` : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </PrototypeCard>

        <SideRail title="运行闸门" meta="Ops">
          <RiskBanner
            status={summary.online === summary.total ? 'pass' : 'warn'}
            title={summary.online === summary.total ? '服务健康通过' : '存在服务异常'}
            detail={`health API 当前在线 ${summary.online} 个，异常 ${summary.offline} 个，检查中 ${summary.checking} 个。`}
          />
          <PrototypeCard title="数据与模型" icon={<DatabaseOutlined />}>
            <div className="li-row">
              <div className="li-badge">PG</div>
              <div className="li-main">
                <div className="n">PostgreSQL 主库</div>
                <div className="s">公共行情与私有对象分域查询</div>
              </div>
            </div>
            <div className="li-row">
              <div className="li-badge">ML</div>
              <div className="li-main">
                <div className="n">{modelHealthy ? '模型服务在线' : '模型服务异常'}</div>
                <div className="s">prediction={serviceStatus.prediction || 'checking'} / training={trainingEnabled ? serviceStatus.training || 'checking' : '未启用'}</div>
              </div>
            </div>
          </PrototypeCard>
          <PrototypeCard title="安全状态" icon={<SafetyCertificateOutlined />}>
            <div className="prototype-panel-note">实盘券商通道需要 broker 配置、风控通过、操作审计三项同时满足才可启用。</div>
          </PrototypeCard>
        </SideRail>
      </div>
    </PrototypePage>
  )
}
