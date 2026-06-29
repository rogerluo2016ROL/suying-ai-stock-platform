import type { ReactNode } from 'react'

export interface MetricCardProps {
  label: ReactNode
  value: ReactNode
  sub?: ReactNode
  tone?: 'up' | 'down' | 'warn' | 'accent' | 'muted'
  className?: string
}

const toneClass: Record<NonNullable<MetricCardProps['tone']>, string> = {
  up: 'up',
  down: 'down',
  warn: '',
  accent: 'neu',
  muted: '',
}

export function MetricCard({ label, value, sub, tone = 'accent', className = '' }: MetricCardProps) {
  const toneStyle = tone === 'warn' ? { color: 'var(--warn)' } : tone === 'muted' ? { color: 'var(--fg-2)' } : undefined

  return (
    <section className={`prototype-metric ${className}`.trim()}>
      <div className="prototype-metric-label">{label}</div>
      <div className={`prototype-metric-value ${toneClass[tone]}`} style={toneStyle}>
        {value}
      </div>
      {sub && <div className="prototype-metric-sub">{sub}</div>}
    </section>
  )
}

export default MetricCard
