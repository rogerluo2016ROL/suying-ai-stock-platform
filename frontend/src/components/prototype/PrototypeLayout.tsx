import type { ReactNode } from 'react'

export interface PageHeaderAction {
  key: string
  label: ReactNode
  active?: boolean
  tone?: 'up' | 'down' | 'warn' | 'neutral'
  onClick?: () => void
}

export interface PrototypePageHeaderProps {
  title: ReactNode
  subtitle?: ReactNode
  actions?: PageHeaderAction[]
  dataFreshness?: ReactNode
}

function actionToneClass(tone?: PageHeaderAction['tone']) {
  if (tone === 'up') return 't-up'
  if (tone === 'down') return 't-down'
  if (tone === 'warn') return 't-warn'
  return 't-mute'
}

export function PrototypePageHeader({ title, subtitle, actions = [], dataFreshness }: PrototypePageHeaderProps) {
  return (
    <header className="page-head">
      <div className="prototype-page-title">
        <h1>{title}</h1>
        {subtitle && <div className="sub">{subtitle}</div>}
        {dataFreshness && <div className="prototype-page-freshness">{dataFreshness}</div>}
      </div>
      {actions.length > 0 && (
        <div className="head-actions">
          {actions.map(action => (
            <button
              key={action.key}
              type="button"
              className={`chip ${action.active ? 'active' : ''} ${actionToneClass(action.tone)}`.trim()}
              onClick={action.onClick}
            >
              {action.label}
            </button>
          ))}
        </div>
      )}
    </header>
  )
}

export interface PrototypePageProps {
  children: ReactNode
  className?: string
}

export function PrototypePage({ children, className = '' }: PrototypePageProps) {
  return <div className={`prototype-page ${className}`.trim()}>{children}</div>
}

export interface PrototypeCardProps {
  title?: ReactNode
  meta?: ReactNode
  icon?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
}

export function PrototypeCard({ title, meta, icon, children, className = '', bodyClassName = '' }: PrototypeCardProps) {
  return (
    <section className={`prototype-card card ${className}`.trim()}>
      {(title || meta || icon) && (
        <div className="card-h">
          {icon && <span className="ic">{icon}</span>}
          {title && <h3>{title}</h3>}
          {meta && <span className="meta">{meta}</span>}
        </div>
      )}
      <div className={`prototype-card-body card-b ${bodyClassName}`.trim()}>
        {children}
      </div>
    </section>
  )
}

export interface PrototypeFallbackProps {
  title: ReactNode
  detail?: ReactNode
}

export function PrototypeFallback({ title, detail }: PrototypeFallbackProps) {
  return (
    <div className="prototype-fallback" role="status">
      <strong>{title}</strong>
      {detail && <div className="prototype-panel-note">{detail}</div>}
    </div>
  )
}
