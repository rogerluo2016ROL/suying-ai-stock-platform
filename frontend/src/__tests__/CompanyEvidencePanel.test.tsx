import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import CompanyEvidencePanel from '../pages/supply-chain-bom/CompanyEvidencePanel'
import type { CandidateCompany } from '../pages/supply-chain-bom/types'

const company: CandidateCompany = {
  code: '301526',
  name: '国际复材',
  node_id: 'semiconductor_materials',
  node_name: '材料',
  mapping_status: 'pending_review',
  mapping_confidence: 0.8,
  mapping_source: 'introduction',
  products: ['电子级玻璃布'],
  evidence_gaps: ['是否有明确客户或供应链认证'],
  financial_indicators: { revenue_growth: 12.3, profit_growth: 22.4, roe: 11.2, gross_margin: 33.1 },
  moat_evidence: [{ evidence_type: 'moat_signal', summary: '电子级玻璃布' }],
}

it('shows evidence and submits review decision', async () => {
  const onReview = vi.fn().mockResolvedValue(undefined)
  render(
    <ConfigProvider locale={zhCN}>
      <CompanyEvidencePanel company={company} onReview={onReview} />
    </ConfigProvider>,
  )

  expect(screen.getByText('国际复材')).toBeInTheDocument()
  expect(screen.getAllByText('电子级玻璃布').length).toBeGreaterThan(0)
  expect(screen.getByText('是否有明确客户或供应链认证')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('tab', { name: '复核' }))
  fireEvent.click(screen.getByRole('button', { name: /确认/ }))
  await waitFor(() => {
    expect(onReview).toHaveBeenCalledWith('301526', 'semiconductor_materials', 'verified')
  })
})
