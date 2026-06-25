import type { CandidateCompany } from './types'
import { formatNumber } from './formatters'

export function evidenceQuality(company: CandidateCompany) {
  const confidenceScore = Math.min(60, Math.max(0, (company.mapping_confidence || 0) * 60))
  const evidenceScore = Math.min(20, (company.moat_evidence || company.evidence || []).length * 10)
  const reportScore = (company.report_titles || []).length > 0 ? 8 : 0
  const sourceScore = company.mapping_source ? 8 : 0
  const gapPenalty = Math.min(20, (company.evidence_gaps || []).length * 7)
  const score = Math.max(0, Math.min(100, Math.round(confidenceScore + evidenceScore + reportScore + sourceScore - gapPenalty)))

  if (score >= 85) return { score, label: '强证据', color: 'green' }
  if (score >= 70) return { score, label: '可跟踪', color: 'blue' }
  if (score >= 50) return { score, label: '待补证', color: 'orange' }
  return { score, label: '弱证据', color: 'red' }
}

function csvCell(value: unknown) {
  const text = Array.isArray(value) ? value.join('、') : String(value ?? '')
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

export function buildResearchExportCsv(candidates: CandidateCompany[]) {
  const header = ['代码', '名称', '节点', '调整分', '映射状态', '映射置信度', '证据评分', '证据来源', '产品', '证据缺口', '研报']
  const rows = candidates.map((company) => {
    const quality = evidenceQuality(company)
    return [
      company.code,
      company.name || '',
      company.node_name || company.layer || '',
      formatNumber(company.mapping_adjusted_score ?? company.score, 1),
      company.mapping_status || '',
      formatNumber(company.mapping_confidence, 2),
      quality.score,
      company.mapping_source || '',
      company.products || [],
      company.evidence_gaps || [],
      company.report_titles || [],
    ].map(csvCell).join(',')
  })
  return [header.join(','), ...rows].join('\n')
}

export function downloadResearchExport(candidates: CandidateCompany[], selectedNodeName?: string) {
  const csv = buildResearchExportCsv(candidates)
  const blob = new Blob([`\ufeff${csv}`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `supply-chain-research-${selectedNodeName || 'candidates'}.csv`
  link.click()
  URL.revokeObjectURL(url)
}
