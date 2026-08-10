import type { CandidatePoolRecord, ChainCandidate, Position, RiskVerdictRecord, StockSignal, TradeOrder } from '../../api/types'
import type { AiSentimentReason, AuctionRow, CandidateRow, DashboardAuctionPick, OrderRow, PositionRow, SectorRow, SignalRow } from './types'

export const overnightNews: Array<{ type: string; tone: string; title: string; impact: string; time: string }> = []

export function num(value: unknown, fallback = 0) {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

export function formatMoney(value?: number) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '-'
  if (Math.abs(value) >= 10000) return `${(value / 10000).toFixed(1)}万`
  return value.toLocaleString('zh-CN', { maximumFractionDigits: 0 })
}

export function formatPct(value?: number) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '-'
  const normalized = Math.abs(value) <= 1 ? value * 100 : value
  return `${normalized >= 0 ? '+' : ''}${normalized.toFixed(1)}%`
}

export function currentTimeText() {
  return new Date().toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit' })
}

export function signalLabel(level: StockSignal['level']) {
  const labels: Record<StockSignal['level'], string> = {
    strong_buy: '强买',
    buy: '买入',
    hold: '观察',
    sell: '减仓',
    strong_sell: '强卖',
  }
  return labels[level] || level
}

export function signalLabelFromApi(signal: StockSignal) {
  if (signal.level) return signalLabel(signal.level)
  const raw = String((signal as StockSignal & { signal?: string }).signal || '').toLowerCase()
  if (raw.includes('bear') || raw.includes('sell') || raw.includes('空')) return '减仓'
  if (raw.includes('bull') || raw.includes('buy') || raw.includes('多')) return '买入'
  return '观察'
}

export function orderStatusLabel(status?: string) {
  const labels: Record<string, string> = {
    pending: '待成交',
    filled: '已成交',
    partial: '部分成交',
    cancelled: '已撤单',
    rejected: '已拒绝',
  }
  return labels[String(status || '')] || String(status || '-')
}

export function candidateRisk(candidate: ChainCandidate, verdicts: RiskVerdictRecord[]) {
  const verdict = verdicts.find(item => item.symbol === candidate.code || item.candidate_id === candidate.candidate_id)
  if (!verdict) return '待风控'
  if (verdict.result === 'pass') return '通过'
  if (verdict.result === 'warn' || verdict.result === 'manual_review') return '仓位复核'
  return '止损'
}

export function sectorRowsFromCandidates(candidates: ChainCandidate[]): SectorRow[] {
  const buckets = new Map<string, ChainCandidate[]>()
  candidates.forEach(candidate => {
    const sector = candidate.industry || candidate.resonance_level || '未分组'
    buckets.set(sector, [...(buckets.get(sector) || []), candidate])
  })
  return Array.from(buckets.entries())
    .map(([name, rows]) => {
      const avg = rows.reduce((sum, row) => sum + num(row.last_change_pct ?? row.change_pct), 0) / Math.max(rows.length, 1)
      const lead = rows
        .slice(0, 2)
        .map(row => `${row.name || row.code} ${formatPct(row.last_change_pct ?? row.change_pct)}`)
        .join(' / ')
      return { name, count: rows.length, change: Number(avg.toFixed(1)), lead: lead || '-', width: Math.min(96, Math.max(16, Math.round(avg * 12 + 48))) }
    })
    .sort((a, b) => b.count - a.count || b.change - a.change)
}

export function signalRowsFromApi(signals: StockSignal[], verdicts: RiskVerdictRecord[]): SignalRow[] {
  return signals.map(signal => {
    const score = Math.round(num(signal.score ?? signal.confidence, 0))
    const fallbackReason = (signal as StockSignal & { fallback_reason?: string }).fallback_reason
    const dimensions = [
      { label: '技术面', value: Math.round(num(signal.dimensions?.technical, score)) },
      { label: '资金面', value: Math.round(num(signal.dimensions?.money_flow, score)) },
      { label: '基本面', value: Math.round(num(signal.dimensions?.fundamental, score)) },
      { label: '情绪', value: Math.round(num(signal.dimensions?.sentiment, score)) },
      { label: '置信度', value: Math.round(num(signal.confidence, score)) },
      { label: '风控', value: verdicts.some(item => item.symbol === signal.code && item.result !== 'pass') ? 45 : 78 },
    ]
    const risk = verdicts.some(item => item.symbol === signal.code && item.result === 'reject')
      ? '止损'
      : verdicts.some(item => item.symbol === signal.code && (item.result === 'warn' || item.result === 'manual_review'))
        ? '仓位复核'
        : '通过'
    return {
      code: signal.code,
      name: signal.name || signal.code,
      price: typeof (signal as StockSignal & { price?: number }).price === 'number'
        ? String((signal as StockSignal & { price?: number }).price)
        : '-',
      signal: signalLabelFromApi(signal),
      score,
      kronos: fallbackReason ? '模型不可用' : '-',
      target: '-',
      confidence: Math.round(num(signal.confidence, score)),
      consistency: fallbackReason ? '待确认' : '双确认',
      risk,
      action: risk === '止损' ? '排除' : risk === '仓位复核' ? '降低优先级' : '确认买入',
      watchlist: false,
      dimensions,
    }
  })
}

export function candidateRowsFromApi(candidates: ChainCandidate[], verdicts: RiskVerdictRecord[]): CandidateRow[] {
  return candidates.map(candidate => ({
    code: candidate.code,
    name: candidate.name || candidate.code,
    source: candidate.trade_signal || candidate.resonance_level || '产业链候选',
    score: Math.round(num(candidate.score ?? candidate.resonance_score ?? candidate.chokepoint_score, 0)),
    risk: candidateRisk(candidate, verdicts),
    size: `${Math.max(5, Math.min(30, Math.round(num(candidate.score ?? 50, 50) / 4)))}%`,
  }))
}

/**
 * 把 screener 持久化候选池记录（queryCandidatePool 返回）摊平成 CandidateRow。
 * 契约 §9.3：scope 不走明文入参，由后端拦截器头（X-Tenant/Owner/Trade-Account）注入；
 * 前端只透传 source_module / source_mode 等查询参数。
 */
export function candidateRowsFromPool(records: CandidatePoolRecord[], verdicts: RiskVerdictRecord[]): CandidateRow[] {
  const seen = new Set<string>()
  return records.flatMap(record => {
    const sourceLabel = `${record.source_module}/${record.source_mode}`
    return (record.candidates || []).map(item => {
      if (!item.code || seen.has(item.code)) return null
      seen.add(item.code)
      const verdict = verdicts.find(v => v.symbol === item.code)
      const risk = !verdict ? '待风控'
        : verdict.result === 'pass' ? '通过'
        : (verdict.result === 'warn' || verdict.result === 'manual_review') ? '仓位复核'
        : '止损'
      return {
        code: item.code,
        name: item.name || item.code,
        source: sourceLabel,
        score: Math.round(num(item.score, 0)),
        risk,
        size: `${Math.max(5, Math.min(30, Math.round(num(item.score, 50) / 4)))}%`,
      }
    }).filter((row): row is CandidateRow => row !== null)
  })
}

/**
 * 决策概览的 AI 解读：3 条支撑原因（趋势 / 资金 / 信号-候选共振）。
 * 后端尚未返回独立 AI reasons 字段时，从 signal/live + 候选池派生，缺字段显式 fallback_reason，不空白。
 */
export function buildAiSentimentReasons(input: {
  avgScore: number
  strongSignals: number
  candidateCount: number
  sectors: SectorRow[]
}): AiSentimentReason[] {
  const { avgScore, strongSignals, candidateCount, sectors } = input
  const topSector = sectors[0]
  return [
    {
      title: '支撑原因 1 · 情绪趋势',
      detail: avgScore > 0
        ? `signal/live 平均评分 ${avgScore}，处于${avgScore >= 70 ? '偏强区间，趋势环境对做多友好' : avgScore >= 50 ? '中性区间，需开盘确认方向' : '偏弱区间，建议谨慎'}。`
        : 'fallback_reason：signal/live 未返回有效评分，情绪趋势暂无法量化，待实时信号补齐。',
      fallback: avgScore === 0,
    },
    {
      title: '支撑原因 2 · 资金面',
      detail: topSector
        ? `${topSector.name} 板块共振居前（+${topSector.change}%），资金面倾向${topSector.change >= 2 ? '活跃流入' : '温和参与'}；实时北向/主力净流入字段未接入，本条仅以板块聚合推断。`
        : 'fallback_reason：暂无板块共振与实时资金接口，资金面支撑原因待后端补齐。',
      fallback: !topSector,
    },
    {
      title: '支撑原因 3 · 信号-候选共振',
      detail: (strongSignals > 0 || candidateCount > 0)
        ? `强信号 ${strongSignals} 只 × 候选池 ${candidateCount} 只，共振${strongSignals >= 2 ? '较强' : '一般'}；开盘后结合竞价意图进一步收敛。`
        : 'fallback_reason：signal/live 与候选池均无数据，信号-候选共振待接口返回。',
      fallback: strongSignals === 0 && candidateCount === 0,
    },
  ]
}

export function auctionRowsFromSignals(signals: SignalRow[], candidates: CandidateRow[]): AuctionRow[] {
  const source = signals.length
    ? signals.map(row => ({ code: row.code, name: row.name, score: row.score, gap: Math.max(0, Math.round((row.score - 50) / 8)), vol: Math.max(1, Number((row.confidence / 12).toFixed(1))), intent: row.score >= 75 ? '强烈抢筹' : '偏多抢筹' }))
    : candidates.map(row => ({ code: row.code, name: row.name, score: row.score, gap: Math.max(0, Math.round((row.score - 50) / 8)), vol: Math.max(1, Number((row.score / 12).toFixed(1))), intent: row.score >= 75 ? '强烈抢筹' : '偏多抢筹' }))
  return source.sort((a, b) => b.score - a.score)
}

export function auctionIntentFromScore(score: number) {
  if (score >= 75) return '强烈抢筹'
  if (score >= 60) return '偏多抢筹'
  if (score >= 40) return '中性观察'
  if (score >= 25) return '偏空出货'
  return '强烈出货'
}

export function auctionRowsFromDashboard(auction: Record<string, unknown>) {
  const picks = Array.isArray(auction.picks) ? auction.picks as DashboardAuctionPick[] : []
  const rows = picks
    .filter(pick => pick.code)
    .map(pick => {
      const score = Math.round(num(pick.score, 0))
      const gap = num(pick.gap_pct ?? pick.chg_pct, 0)
      const vol = Math.max(0.1, Number(num(pick.vol_ratio ?? pick.volume_ratio ?? pick.vol_z, 1).toFixed(1)))
      return {
        code: String(pick.code),
        name: pick.name || String(pick.code),
        industry: pick.industry,
        gap,
        vol,
        score,
        intent: pick.intent || auctionIntentFromScore(score),
      }
    })
    .sort((a, b) => b.score - a.score)

  return {
    bullish: rows.filter(row => row.score >= 40 || num(row.gap, 0) >= 0).slice(0, 10),
    bearish: rows.filter(row => row.score < 40 && num(row.gap, 0) < 0).slice(0, 10),
  }
}

export function bearishRowsFromSignals(signals: SignalRow[]): AuctionRow[] {
  return signals
    .filter(row => (row.signal || '').includes('减') || (row.signal || '').includes('卖') || row.risk !== '通过')
    .map(row => ({ code: row.code, name: row.name, score: row.score, drop: -Math.max(1, Math.round((60 - row.score) / 8)), vol: Math.max(1, Number((row.confidence / 15).toFixed(1))), intent: row.risk === '止损' ? '强烈出货' : '偏空出货' }))
}

export function orderRowsFromApi(rows: TradeOrder[]): OrderRow[] {
  return rows.map(row => ({
    time: (row.created_at || row.filled_at || '-').slice(11, 19) || '-',
    code: row.code,
    name: row.name || row.code,
    dir: String(row.direction).toLowerCase() === 'sell' ? '卖出' : '买入',
    price: String(row.filled_price ?? row.price ?? '-'),
    qty: Number(row.filled_volume ?? row.volume ?? 0).toLocaleString('zh-CN'),
    status: orderStatusLabel(row.status),
  }))
}

export function positionRowsFromApi(rows: Position[], totalMarketValue?: number): PositionRow[] {
  const total = totalMarketValue || rows.reduce((sum, row) => sum + num(row.market_value), 0)
  return rows.map(row => ({
    code: row.code,
    name: row.name || row.code,
    value: formatMoney(row.market_value),
    pnl: formatPct(row.pnl_pct),
    weight: total ? `${Math.round((num(row.market_value) / total) * 100)}%` : '-',
  }))
}

export function activeKey(pathname: string) {
  if (pathname.endsWith('/auction')) return 'auction'
  if (pathname.endsWith('/signals')) return 'signals'
  if (pathname.endsWith('/candidates')) return 'candidates'
  if (pathname.endsWith('/execution')) return 'execution'
  return 'overview'
}

export function toneForRisk(risk: string) {
  if (risk === '通过') return 't-down'
  if (risk.includes('复核')) return 't-warn'
  return 't-mute'
}

export function decisionHeader(activeLabel: string) {
  if (activeLabel === '信号扫描') return '验证工作台 · 逐条确认信号 · Kronos 交叉验证 · 一键推送候选池'
  if (activeLabel === '候选池') return '候选池: 竞价 + 信号 + 选股 + 自选 -> 多源融合去重'
  if (activeLabel === '执行监控') return '订单: trade-service (orders) | 持仓: trade-service (positions)'
  return '竞价分析 · 信号扫描 · 候选池 · 执行监控'
}
