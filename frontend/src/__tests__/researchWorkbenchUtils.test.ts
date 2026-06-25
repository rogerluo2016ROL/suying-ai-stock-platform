import { buildResearchExportCsv, evidenceQuality } from '../pages/supply-chain-bom/researchWorkbenchUtils'
import type { CandidateCompany } from '../pages/supply-chain-bom/types'

const company: CandidateCompany = {
  code: '301526',
  name: '国际复材',
  node_name: '材料',
  mapping_confidence: 0.82,
  mapping_status: 'pending_review',
  mapping_source: 'introduction',
  mapping_adjusted_score: 84,
  products: ['电子级玻璃布'],
  report_titles: ['电子材料国产替代'],
  moat_evidence: [
    { evidence_type: 'product', summary: '电子级玻璃布' },
    { evidence_type: 'customer', summary: '下游认证推进' },
  ],
  evidence_gaps: ['客户名单待补'],
}

it('scores evidence quality from confidence, sources, and gaps', () => {
  const quality = evidenceQuality(company)

  expect(quality.score).toBe(78)
  expect(quality.label).toBe('可跟踪')
  expect(quality.color).toBe('blue')
})

it('builds a CSV research export with candidate evidence fields', () => {
  const csv = buildResearchExportCsv([company])

  expect(csv).toContain('代码,名称,节点,调整分,映射状态,映射置信度,证据评分,证据来源,产品,证据缺口,研报')
  expect(csv).toContain('301526,国际复材,材料,84.0,pending_review,0.82,78,introduction,电子级玻璃布,客户名单待补,电子材料国产替代')
})
