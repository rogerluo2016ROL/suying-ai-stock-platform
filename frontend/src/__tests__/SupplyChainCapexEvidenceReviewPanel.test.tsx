import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ConfigProvider, App as AntdApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import SupplyChainCapexEvidenceReviewPanel from '../pages/supply-chain-bom/SupplyChainCapexEvidenceReviewPanel'
import { screenerApi } from '../api/client'

vi.mock('../api/client', () => ({
  screenerApi: {
    getSupplyChainCapexEvidenceReviewQueue: vi.fn(),
    reviewSupplyChainCapexEvidence: vi.fn(),
  },
}))

describe('SupplyChainCapexEvidenceReviewPanel', () => {
  beforeEach(() => {
    vi.mocked(screenerApi.getSupplyChainCapexEvidenceReviewQueue).mockReset()
    vi.mocked(screenerApi.reviewSupplyChainCapexEvidence).mockReset()
    vi.mocked(screenerApi.getSupplyChainCapexEvidenceReviewQueue).mockResolvedValue({
      data: {
        version: 'business-tag-capex-evidence-review-queue-v1',
        source_status: 'ready',
        filters: { limit: 80, chain_id: 'ai_compute', review_status: 'pending_review' },
        counts: { pending_review: 51, approved: 0, rejected: 0 },
        queue: [
          {
            capex_evidence_id: 'capex-1',
            mapping_id: '18C-MAP-ai_compute-300308SZ',
            code: '300308',
            company_name: '中际旭创',
            chain_id: 'ai_compute',
            tag_name: '高速光模块',
            fiscal_period: '2026Q1',
            as_of_date: '2026-07-07',
            capex_direction: ['高速光模块产能投入', 'AI算力需求配套'],
            mapped_layer_id: 'infrastructure',
            mapped_segments: ['高速光模块', 'AI 数据中心'],
            source_type: 'research_title',
            source_level: 'mid',
            source_name: 'evidence_extracted_facts:FACT-1',
            quote: '公司事件点评报告：高速光模块需求强劲增长，进一步加大产能投入',
            evidence_level: 'directional',
            confidence: 0.6,
            review_status: 'pending_review',
            direction_is_ai_related: true,
          },
        ],
        limitations: [],
      },
    } as any)
    vi.mocked(screenerApi.reviewSupplyChainCapexEvidence).mockResolvedValue({ data: {} } as any)
  })

  it('renders CAPEX evidence review queue and approves one row', async () => {
    render(
      <ConfigProvider locale={zhCN}>
        <AntdApp>
          <SupplyChainCapexEvidenceReviewPanel />
        </AntdApp>
      </ConfigProvider>,
    )

    expect(await screen.findByText('CAPEX 证据审核')).toBeInTheDocument()
    expect(screen.getByText('中际旭创')).toBeInTheDocument()
    expect(screen.getByText('高速光模块产能投入')).toBeInTheDocument()
    expect(screen.getByText(/进一步加大产能投入/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /批准/ }))

    await waitFor(() => {
      expect(screenerApi.reviewSupplyChainCapexEvidence).toHaveBeenCalledWith('capex-1', expect.objectContaining({
        review_status: 'approved',
        reviewer: 'frontend',
      }))
    })
  })
})
