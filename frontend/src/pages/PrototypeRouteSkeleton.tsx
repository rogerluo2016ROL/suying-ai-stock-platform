import { useMemo } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  DataDomainBadge,
  EmptyState,
  LineageChips,
  MetricCard,
  PrototypeCard,
  PrototypePage,
  PrototypePageHeader,
  PrototypeTabs,
  RiskBanner,
  SideRail,
} from '../components/prototype'

export interface PrototypeRouteTab {
  key: string
  path: string
  label: string
  subLabel: string
}

export interface PrototypeRouteMetric {
  label: string
  value: string
  sub: string
  tone?: 'up' | 'down' | 'warn' | 'accent' | 'muted'
}

export interface PrototypeRouteRow {
  label: string
  value: string
  meta: string
  tone?: 'up' | 'down' | 'warn' | 'accent' | 'muted'
}

export interface PrototypeRouteSkeletonConfig {
  title: string
  subtitle: string
  tabs: PrototypeRouteTab[]
  metrics: PrototypeRouteMetric[]
  primaryTitle: string
  primaryMeta: string
  rows: PrototypeRouteRow[]
  railTitle: string
  railMeta: string
  riskTitle: string
  riskDetail: string
  emptyTitle: string
  emptyDetail: string
}

function toneClass(tone?: PrototypeRouteRow['tone']) {
  if (tone === 'up') return 'up'
  if (tone === 'down') return 'down'
  if (tone === 'warn') return 'warn'
  if (tone === 'accent') return 'neu'
  return ''
}

export function PrototypeRouteSkeleton({ config }: { config: PrototypeRouteSkeletonConfig }) {
  const location = useLocation()
  const navigate = useNavigate()
  const activeTab = useMemo(
    () => config.tabs.find(tab => tab.path === location.pathname) ?? config.tabs[0],
    [config.tabs, location.pathname],
  )

  return (
    <PrototypePage>
      <PrototypeTabs
        ariaLabel={`${config.title}页签`}
        activeKey={activeTab.key}
        onChange={(key) => {
          const tab = config.tabs.find(item => item.key === key)
          if (tab) navigate(tab.path)
        }}
        items={config.tabs.map((tab, index) => ({ ...tab, number: String(index + 1).padStart(2, '0') }))}
      />
      <PrototypePageHeader
        title={`${config.title} - ${activeTab.label}`}
        subtitle={config.subtitle}
        actions={[
          { key: 'public', label: '公共数据' },
          { key: 'private', label: '账户私有', active: true, tone: 'neutral' },
          { key: 'ready', label: '数据同步中', tone: 'warn' },
        ]}
      />
      <div className="kpis">
        {config.metrics.map(item => (
          <MetricCard key={item.label} label={item.label} value={item.value} sub={item.sub} tone={item.tone ?? 'accent'} />
        ))}
      </div>
      <div className="row r-6-4">
        <PrototypeCard title={config.primaryTitle} meta={config.primaryMeta}>
          <table className="tbl">
            <thead>
              <tr>
                <th>对象</th>
                <th>状态</th>
                <th className="r">说明</th>
              </tr>
            </thead>
            <tbody>
              {config.rows.map(row => (
                <tr key={row.label}>
                  <td className="nm">{row.label}</td>
                  <td className={toneClass(row.tone)}>{row.value}</td>
                  <td className="r">{row.meta}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </PrototypeCard>
        <SideRail title={config.railTitle} meta={config.railMeta}>
          <DataDomainBadge domain="account" label="账户私有" />
          <LineageChips
            items={[
              { label: '候选', value: 'CAND-*' },
              { label: '方案', value: 'PLAN-*' },
              { label: '风控', value: 'RV-*', tone: 'warn' },
            ]}
          />
          <RiskBanner status="warn" title={config.riskTitle} detail={config.riskDetail} />
          <EmptyState title={config.emptyTitle} detail={config.emptyDetail} actionLabel="刷新" />
        </SideRail>
      </div>
    </PrototypePage>
  )
}
