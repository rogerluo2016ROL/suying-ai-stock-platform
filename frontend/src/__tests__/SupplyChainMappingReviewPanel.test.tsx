import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import SupplyChainMappingReviewPanel from '../pages/supply-chain-bom/SupplyChainMappingReviewPanel'
import { screenerApi } from '../api/client'

vi.mock('../api/client', () => ({
  screenerApi: {
    getSupplyChainMappingQuality: vi.fn(),
    getSupplyChainMappingReviewQueue: vi.fn(),
    reviewSupplyChainMapping: vi.fn(),
  },
}))

const quality = {
  mapping_count: 15642,
  review_queue_count: 14573,
  status_counts: {
    verified: 1069,
    pending_review: 10547,
    weak_evidence: 4026,
  },
  source_counts: {
    main_business: 4366,
  },
  hotspot_nodes: [
    {
      node_id: 'advanced_manufacturing_integration',
      node_name: '集成',
      chain_id: 'advanced_manufacturing',
      verified: 24,
      pending_review: 846,
      weak_evidence: 68,
      rejected: 0,
      review_pressure: 914,
    },
  ],
}

const queue = {
  total: 14573,
  limit: 20,
  offset: 0,
  items: [
    {
      code: '301526',
      name: '国际复材',
      node_id: 'semiconductor_materials',
      node_name: '材料',
      chain_id: 'semiconductor',
      product_name: '电子级玻璃布',
      confidence: 0.8,
      status: 'pending_review',
      mapping_source: 'introduction',
      evidence: ['电子级玻璃布'],
      evidence_gaps: ['是否有明确客户或供应链认证'],
      review_priority: 92,
    },
  ],
}

describe('SupplyChainMappingReviewPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(screenerApi.getSupplyChainMappingQuality).mockResolvedValue({ data: quality } as any)
    vi.mocked(screenerApi.getSupplyChainMappingReviewQueue).mockResolvedValue({ data: queue } as any)
    vi.mocked(screenerApi.reviewSupplyChainMapping).mockResolvedValue({
      data: { status: 'ok', mapping_status: 'verified' },
    } as any)
  })

  it('renders quality counts and review queue without wrapping table content', async () => {
    render(
      <ConfigProvider locale={zhCN}>
        <SupplyChainMappingReviewPanel />
      </ConfigProvider>,
    )

    expect(await screen.findByText('映射复核')).toBeInTheDocument()
    expect(screen.getByText('14,573')).toBeInTheDocument()
    expect(screen.getByText('高端制造/集成')).toBeInTheDocument()
    expect(screen.getByText('国际复材')).toBeInTheDocument()
    expect(screen.getByText('电子级玻璃布')).toBeInTheDocument()
    expect(screen.getByTestId('mapping-review-table-wrap')).toHaveStyle({ whiteSpace: 'nowrap' })
  })

  it('reloads queue for a selected hotspot node', async () => {
    render(
      <ConfigProvider locale={zhCN}>
        <SupplyChainMappingReviewPanel />
      </ConfigProvider>,
    )

    fireEvent.click(await screen.findByRole('button', { name: /查看/ }))

    await waitFor(() => {
      expect(screenerApi.getSupplyChainMappingReviewQueue).toHaveBeenCalledWith({
        status: 'reviewable',
        nodeId: 'advanced_manufacturing_integration',
        limit: 20,
        offset: 0,
      })
    })
  })

  it('submits a verified decision and refreshes quality data', async () => {
    render(
      <ConfigProvider locale={zhCN}>
        <SupplyChainMappingReviewPanel />
      </ConfigProvider>,
    )

    fireEvent.click(await screen.findByRole('button', { name: /确认/ }))

    await waitFor(() => {
      expect(screenerApi.reviewSupplyChainMapping).toHaveBeenCalledWith(
        '301526',
        'semiconductor_materials',
        { decision: 'verified', reviewer: 'frontend', note: '前端复核确认' },
      )
    })
    expect(screenerApi.getSupplyChainMappingQuality).toHaveBeenCalledTimes(2)
  })
})
