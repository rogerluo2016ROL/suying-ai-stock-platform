import type { ReactNode } from 'react'

export type DataDomain = 'public' | 'tenant' | 'user' | 'account'
export type PrimitiveTone = 'neutral' | 'accent' | 'safe' | 'warn' | 'danger'

export interface DataDomainBadgeProps {
  domain: DataDomain
  label: ReactNode
}

const domainTone: Record<DataDomain, PrimitiveTone> = {
  public: 'accent',
  tenant: 'neutral',
  user: 'neutral',
  account: 'safe',
}

export function DataDomainBadge({ domain, label }: DataDomainBadgeProps) {
  return (
    <span className={`data-domain-badge ${domainTone[domain]}`} data-domain={domain}>
      {label}
    </span>
  )
}

export interface LineageChip {
  label: ReactNode
  value: ReactNode
  tone?: PrimitiveTone
}

export interface LineageChipsProps {
  items: LineageChip[]
}

export function LineageChips({ items }: LineageChipsProps) {
  if (items.length === 0) return null
  return (
    <div className="lineage-chips" aria-label="链路追踪">
      {items.map((item, index) => (
        <span className={`lineage-chip ${item.tone ?? 'neutral'}`} key={`${item.label}-${index}`}>
          <span>{item.label}</span>
          <b>{item.value}</b>
        </span>
      ))}
    </div>
  )
}

export interface RiskBannerProps {
  status: 'pass' | 'warn' | 'reject' | 'review'
  title: ReactNode
  detail?: ReactNode
}

function riskTone(status: RiskBannerProps['status']) {
  if (status === 'pass') return 'safe'
  if (status === 'reject') return 'danger'
  if (status === 'review') return 'accent'
  return 'warn'
}

export function RiskBanner({ status, title, detail }: RiskBannerProps) {
  return (
    <div className={`risk-banner ${riskTone(status)}`} role="status">
      <strong>{title}</strong>
      {detail && <span>{detail}</span>}
    </div>
  )
}

export interface EmptyStateProps {
  title: ReactNode
  detail?: ReactNode
  actionLabel?: ReactNode
  onAction?: () => void
}

export function EmptyState({ title, detail, actionLabel, onAction }: EmptyStateProps) {
  return (
    <div className="prototype-empty-state">
      <strong>{title}</strong>
      {detail && <span>{detail}</span>}
      {actionLabel && (
        <button type="button" className="btn sm ghost" onClick={onAction}>
          {actionLabel}
        </button>
      )}
    </div>
  )
}

export interface SideRailProps {
  title: ReactNode
  meta?: ReactNode
  children: ReactNode
}

export function SideRail({ title, meta, children }: SideRailProps) {
  return (
    <aside className="side-rail">
      <div className="side-rail-head">
        <h3>{title}</h3>
        {meta && <span>{meta}</span>}
      </div>
      <div className="side-rail-body">{children}</div>
    </aside>
  )
}

