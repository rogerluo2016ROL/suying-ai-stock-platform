export const dimensionLabel: Record<string, string> = {
  policy: '政策力度',
  bom: 'BOM关键度',
  chokepoint: '卡脖子',
  growth: '业绩成长',
  profit: '盈利质量',
  commercialization: '商业化阶段',
  moat: '护城河',
  market: '市场共振',
  risk: '风险扣分',
}

export function scoreColor(score?: number) {
  if ((score || 0) >= 80) return 'red'
  if ((score || 0) >= 65) return 'green'
  if ((score || 0) >= 50) return 'blue'
  return 'default'
}

export function formatNumber(value: unknown, digits = 1) {
  const n = Number(value)
  if (!Number.isFinite(n)) return '--'
  return n.toFixed(digits)
}
