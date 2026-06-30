type FreshnessValue = string | number | null | undefined

export interface DataFreshnessBarProps {
  tradeDate?: FreshnessValue
  updatedAt?: FreshnessValue
  source?: FreshnessValue
  currentTradeDate?: FreshnessValue
  className?: string
}

const MISSING_TRADE_DATE = '后端未返回数据日期'

function asText(value: FreshnessValue) {
  if (value === null || value === undefined || value === '') return ''
  return String(value)
}

export function formatTradeDate(value: FreshnessValue) {
  const text = asText(value).trim()
  if (!text) return MISSING_TRADE_DATE
  if (/^\d{4}-\d{2}-\d{2}/.test(text)) return text.slice(0, 10)
  if (/^\d{8}$/.test(text)) return `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6, 8)}`
  return text
}

export function formatUpdateTime(value: FreshnessValue) {
  const text = asText(value).trim()
  if (!text) return '后端未返回更新时间'
  if (/^\d{2}:\d{2}(:\d{2})?$/.test(text)) return text

  const parsed = new Date(text)
  if (!Number.isNaN(parsed.getTime())) {
    return parsed.toLocaleTimeString('zh-CN', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  }

  return text
}

export function freshnessStatus(tradeDate: FreshnessValue, currentTradeDate?: FreshnessValue) {
  const loaded = formatTradeDate(tradeDate)
  const current = formatTradeDate(currentTradeDate)
  if (loaded === MISSING_TRADE_DATE) return { label: '缺少交易日', tone: 'warn' }
  if (current !== MISSING_TRADE_DATE && loaded < current) return { label: '数据过期', tone: 'danger' }
  return { label: '可用', tone: 'ok' }
}

export function DataFreshnessBar({ tradeDate, updatedAt, source, currentTradeDate, className = '' }: DataFreshnessBarProps) {
  const sourceText = asText(source).trim() || '后端未返回数据源'
  const status = freshnessStatus(tradeDate, currentTradeDate)

  return (
    <div className={`data-freshness-bar ${className}`.trim()} aria-label="数据日期">
      <span className="data-freshness-item">交易日：{formatTradeDate(tradeDate)}</span>
      <span className="data-freshness-item">数据更新：{formatUpdateTime(updatedAt)}</span>
      <span className="data-freshness-item">来源：{sourceText}</span>
      <span className={`data-freshness-item data-freshness-${status.tone}`}>状态：{status.label}</span>
    </div>
  )
}
