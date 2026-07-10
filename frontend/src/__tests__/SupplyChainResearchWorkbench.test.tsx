import { fireEvent, render, screen, within } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import SupplyChainResearchWorkbench from '../pages/supply-chain-bom/SupplyChainResearchWorkbench'
import type { BomNode, CandidateCompany, SelectedNodeThesis, ThemeRow } from '../pages/supply-chain-bom/types'
import type { ChainDeconstructResponse } from '../api/client'

const themes: ThemeRow[] = [
  { theme_id: 'hard_tech', name: '硬核科技', policy_weight: 1.2, keywords: ['半导体'], node_count: 2 },
]

const nodes: BomNode[] = [
  {
    node_id: 'semiconductor_materials',
    theme_id: 'hard_tech',
    chain_id: 'semiconductor',
    level: 'L2',
    name: '材料',
    node_type: 'node',
    keywords: ['电子级玻璃布'],
  },
]

const candidates: CandidateCompany[] = [
  {
    code: '301526',
    name: '国际复材',
    node_id: 'semiconductor_materials',
    node_name: '材料',
    score: 82,
    mapping_adjusted_score: 84,
    mapping_status: 'pending_review',
    mapping_confidence: 0.82,
    products: ['电子级玻璃布'],
    evidence_gaps: ['是否有明确客户或供应链认证'],
  },
]

const thesis: SelectedNodeThesis = {
  node_id: 'semiconductor_materials',
  name: '材料',
  thesis: '关注国产替代材料环节。',
  trigger_conditions: ['客户认证'],
  risk_factors: ['证据不足'],
}

it('coordinates node drilldown, candidate opening, comparison, and review', () => {
  const onSelectTheme = vi.fn()
  const onSelectNode = vi.fn()
  const onOpenCompany = vi.fn()
  const onReviewMapping = vi.fn().mockResolvedValue(undefined)

  render(
    <ConfigProvider locale={zhCN}>
      <SupplyChainResearchWorkbench
        themes={themes}
        nodes={nodes}
        candidates={candidates}
        selectedThemeId="hard_tech"
        selectedNodeId="semiconductor_materials"
        selectedNodeThesis={thesis}
        mappingQuality={{
          mapping_count: 1,
          review_queue_count: 1,
          status_counts: { pending_review: 1 },
          source_counts: {},
          hotspot_nodes: [],
        }}
        onSelectTheme={onSelectTheme}
        onSelectNode={onSelectNode}
        onOpenCompany={onOpenCompany}
        onReviewMapping={onReviewMapping}
      />
    </ConfigProvider>,
  )

  expect(screen.getByText('产业链拆解工作台')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /材料/ }))
  expect(onSelectNode).toHaveBeenCalledWith('semiconductor_materials')

  fireEvent.click(screen.getByRole('button', { name: /国际复材/ }))
  expect(onOpenCompany).toHaveBeenCalledWith(expect.objectContaining({ code: '301526' }))
  expect(screen.getAllByText('是否有明确客户或供应链认证').length).toBeGreaterThan(0)

  fireEvent.click(screen.getByRole('checkbox', { name: /对比 国际复材/ }))
  const compareRegion = screen.getByLabelText('候选对比栏')
  expect(within(compareRegion).getByText('国际复材')).toBeInTheDocument()

  fireEvent.click(screen.getByRole('tab', { name: '复核' }))
  fireEvent.click(screen.getByRole('button', { name: /确认/ }))
  expect(onReviewMapping).toHaveBeenCalledWith('301526', 'semiconductor_materials', 'verified')
})

it('does not render preview-only aggregate numbers or synthetic lineage ids', () => {
  const templateResult = {
    template: { name: 'AI 算力', example_theme: '算力' },
    tree: { children: [{ node_id: 'layer-1', layer_id: 'L1-fake', layer_order: 1, name: '芯片', definition: '定义', segments: ['GPU'] }] },
  } as unknown as ChainDeconstructResponse

  render(
    <ConfigProvider locale={zhCN}>
      <SupplyChainResearchWorkbench
        themes={themes}
        nodes={nodes}
        candidates={candidates}
        chainTemplate="ai_compute_infrastructure"
        templateResult={templateResult}
      />
    </ConfigProvider>,
  )

  expect(document.querySelectorAll('.ant-statistic')).toHaveLength(0)
  expect(screen.queryByText('L1-fake')).not.toBeInTheDocument()
})
