import type { ReactNode } from 'react'

export interface PrototypeTabItem {
  key: string
  label: ReactNode
  subLabel?: ReactNode
  number?: string
}

export interface PrototypeTabsProps {
  items: PrototypeTabItem[]
  activeKey: string
  onChange: (key: string) => void
  ariaLabel: string
}

export function PrototypeTabs({ items, activeKey, onChange, ariaLabel }: PrototypeTabsProps) {
  return (
    <nav className="prototype-tabs" role="tablist" aria-label={ariaLabel}>
      {items.map((item, index) => {
        const active = item.key === activeKey
        return (
          <button
            key={item.key}
            type="button"
            role="tab"
            aria-selected={active}
            className={`prototype-tab ${active ? 'active' : ''}`.trim()}
            aria-current={active ? 'page' : undefined}
            onClick={() => onChange(item.key)}
          >
            <span className="tab-no">{item.number ?? String(index + 1).padStart(2, '0')}</span>
            <span className="prototype-tab-title">{item.label}</span>
            {item.subLabel && <span className="prototype-tab-sub">{item.subLabel}</span>}
          </button>
        )
      })}
    </nav>
  )
}

export interface SegmentTabItem {
  key: string
  label: ReactNode
  count?: ReactNode
}

export interface SegmentTabsProps {
  items: SegmentTabItem[]
  activeKey: string
  onChange: (key: string) => void
  ariaLabel: string
}

export function SegmentTabs({ items, activeKey, onChange, ariaLabel }: SegmentTabsProps) {
  return (
    <div className="seg" role="tablist" aria-label={ariaLabel}>
      {items.map(item => {
        const active = item.key === activeKey
        return (
          <button
            key={item.key}
            type="button"
            className={`s ${active ? 'active' : ''}`.trim()}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(item.key)}
          >
            {item.label}
            {item.count !== undefined && <span className="n">{item.count}</span>}
          </button>
        )
      })}
    </div>
  )
}
