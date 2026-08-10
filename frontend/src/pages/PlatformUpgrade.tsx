import { useEffect, useMemo, useState } from 'react'
import { ApartmentOutlined, CloudServerOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { healthApi, trainingApi, type TrainingModelRecord } from '../api/client'
import { tradeApi } from '../api/domains/trade/api'
import {
  DataDomainBadge,
  DataFreshnessBar,
  LineageChips,
  MetricCard,
  PrototypeCard,
  PrototypePage,
  PrototypePageHeader,
  RiskBanner,
  SideRail,
} from '../components/prototype'

interface PlatformUpgradeState {
  serviceStatus: Record<string, string>
  models: TrainingModelRecord[]
  brokerStatus: Record<string, unknown>
  riskConfig: Record<string, unknown>
  loading: boolean
  error: string
  updatedAt: string
}

const initialState: PlatformUpgradeState = {
  serviceStatus: {},
  models: [],
  brokerStatus: {},
  riskConfig: {},
  loading: true,
  error: '',
  updatedAt: '',
}

function statusText(status?: string) {
  if (!status) return '未知'
  if (status === 'healthy' || status === 'online') return '在线'
  if (status === 'degraded') return '降级'
  return '离线'
}

function brokerMode(status: Record<string, unknown>) {
  const value = status.mode || status.trade_mode || status.environment || status.broker_name
  return value ? String(value) : '未知'
}

function configEnabled(config: Record<string, unknown>, key: string) {
  const value = config[key]
  if (typeof value === 'boolean') return value
  if (typeof value === 'number') return value > 0
  return Boolean(value)
}

export default function PlatformUpgrade() {
  const [state, setState] = useState<PlatformUpgradeState>(initialState)

  useEffect(() => {
    let mounted = true
    Promise.allSettled([
      healthApi.gateway(),
      healthApi.check('auth'),
      healthApi.check('trade'),
      healthApi.check('training'),
      trainingApi.getModels({ page: 1, page_size: 20 }),
      tradeApi.getBrokerStatus(),
      tradeApi.getRiskConfig(),
    ]).then(results => {
      if (!mounted) return
      const [gateway, auth, trade, training, models, broker, risk] = results
      const failed = results.filter(result => result.status === 'rejected').length
      setState({
        serviceStatus: {
          gateway: gateway.status === 'fulfilled' ? gateway.value.data?.status || 'unknown' : 'offline',
          auth: auth.status === 'fulfilled' ? auth.value.data?.status || 'unknown' : 'offline',
          trade: trade.status === 'fulfilled' ? trade.value.data?.status || 'unknown' : 'offline',
          training: training.status === 'fulfilled' ? training.value.data?.status || 'unknown' : 'offline',
        },
        models: models.status === 'fulfilled' ? models.value.data?.models || [] : [],
        brokerStatus: broker.status === 'fulfilled' ? broker.value.data || {} : {},
        riskConfig: risk.status === 'fulfilled' ? risk.value.data || {} : {},
        loading: false,
        error: failed ? `${failed} 个治理接口连接异常` : '',
        updatedAt: new Date().toISOString(),
      })
    })
    return () => {
      mounted = false
    }
  }, [])

  const onlineCount = useMemo(
    () => Object.values(state.serviceStatus).filter(status => status === 'healthy' || status === 'online').length,
    [state.serviceStatus],
  )
  const brokerLabel = brokerMode(state.brokerStatus)
  const hasModels = state.models.length > 0
  const governanceStatus = state.error ? 'warn' : onlineCount === 4 ? 'pass' : 'review'
  const matrixRows = [
    ['公共行情', onlineCount >= 2 ? '共享可用' : '待验证', '只读共享缓存', '不同账号看到同一行情时点'],
    ['自选/方案', statusText(state.serviceStatus.auth), 'tenant_id + owner_user_id', '跨账户不可见'],
    ['交易账户', configEnabled(state.riskConfig, 'max_position_pct') ? '账户级' : '待配置', 'account_id 强绑定', '订单必须绑定账户'],
    ['券商通道', brokerLabel, 'broker_mode + risk gate', '实盘默认锁定'],
    ['云端部署', `${onlineCount}/4 在线`, '网关统一鉴权', '服务可水平扩展'],
  ]

  return (
    <PrototypePage>
      <PrototypePageHeader
        title="平台升级 - 云端多租户"
        subtitle="多租户 · 公私数据隔离 · 云端部署 · 券商适配"
        dataFreshness={<DataFreshnessBar updatedAt={state.updatedAt} source="platform-governance APIs" />}
        actions={[
          { key: 'tenant', label: 'tenant/user/account', active: true, tone: 'neutral' },
          { key: 'broker', label: 'QMT 沙箱优先', tone: 'warn' },
        ]}
      />
      <div className="kpis">
        <MetricCard label="账号隔离" value={statusText(state.serviceStatus.auth)} sub="auth/health" tone="accent" />
        <MetricCard label="公共数据" value={hasModels ? `${state.models.length} models` : '无模型'} sub="training/models" tone={hasModels ? 'up' : 'warn'} />
        <MetricCard label="券商模式" value={brokerLabel} sub="trade/broker/status" tone={brokerLabel === '未知' ? 'warn' : 'accent'} />
        <MetricCard label="云端基线" value={state.loading ? '加载中' : `${onlineCount}/4`} sub={state.error || '网关 + 服务拆分'} tone={state.error ? 'warn' : 'muted'} />
      </div>
      <div className="r r-2-1">
        <PrototypeCard
          title="多租户升级矩阵"
          icon={<ApartmentOutlined />}
          meta={<DataDomainBadge domain="tenant" label="platform-governance" />}
        >
          <table className="tbl">
            <thead>
              <tr>
                <th>能力</th>
                <th>当前状态</th>
                <th>落地要求</th>
                <th>验收口径</th>
              </tr>
            </thead>
            <tbody>
              {matrixRows.map(row => (
                <tr key={row[0]}>
                  <td className="nm">{row[0]}</td>
                  <td>{row[1]}</td>
                  <td>{row[2]}</td>
                  <td>{row[3]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </PrototypeCard>

        <SideRail title="治理边界" meta="Cloud">
          <RiskBanner
            status={governanceStatus}
            title="公共数据 / 私有对象边界"
            detail={state.error || '行情、因子、模型版本共享；自选、候选池、方案、订单、风控判定按租户/用户/账户隔离。'}
          />
          <PrototypeCard title="迁移链路" icon={<CloudServerOutlined />}>
            <LineageChips
              items={[
                { label: 'Auth', value: statusText(state.serviceStatus.auth), tone: 'accent' },
                { label: 'Model', value: String(state.models.length), tone: 'safe' },
                { label: 'Trade', value: brokerLabel, tone: brokerLabel === '未知' ? 'warn' : 'safe' },
              ]}
            />
            <div className="prototype-panel-note" style={{ marginTop: 10 }}>
              前端上下文负责传递 tenant/user/account/trade_mode，后端服务按字段做强过滤；当前 gateway/trade/training 在线数 {onlineCount}/4。
            </div>
          </PrototypeCard>
          <PrototypeCard title="券商接入" icon={<SafetyCertificateOutlined />}>
            <div className="prototype-panel-note">当前券商模式: {brokerLabel}；风控配置: {Object.keys(state.riskConfig).length ? '已读取' : '未读取'}。实盘必须保留人工确认与审计。</div>
          </PrototypeCard>
        </SideRail>
      </div>
    </PrototypePage>
  )
}
