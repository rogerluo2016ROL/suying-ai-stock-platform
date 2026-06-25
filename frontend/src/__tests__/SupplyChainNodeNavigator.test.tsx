import { fireEvent, render, screen } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import SupplyChainNodeNavigator from '../pages/supply-chain-bom/SupplyChainNodeNavigator'

const themes = [{
  theme_id: 'future_industry_core',
  name: '未来产业主攻方向',
  policy_weight: 1.5,
  keywords: [],
  node_count: 1,
}]

const nodes = [{
  node_id: 'semiconductor_materials',
  theme_id: 'future_industry_core',
  chain_id: 'semiconductor',
  level: 'layer',
  name: '材料',
  node_type: 'layer',
  keywords: ['光刻胶'],
  policy_theme: '未来产业主攻方向',
}]

const quality = {
  mapping_count: 15642,
  review_queue_count: 14573,
  status_counts: { verified: 1069, pending_review: 10547, weak_evidence: 4026 },
  source_counts: {},
  hotspot_nodes: [{
    node_id: 'semiconductor_materials',
    node_name: '材料',
    chain_id: 'semiconductor',
    pending_review: 460,
    weak_evidence: 82,
    verified: 38,
    rejected: 0,
    review_pressure: 542,
  }],
}

it('shows hotspot pressure and selects a node', () => {
  const onSelectNode = vi.fn()
  render(
    <ConfigProvider locale={zhCN}>
      <SupplyChainNodeNavigator
        themes={themes}
        nodes={nodes}
        selectedThemeId="future_industry_core"
        selectedNodeId=""
        quality={quality}
        selectedNodeThesis={{}}
        candidateCount={0}
        evidenceCount={0}
        onSelectTheme={() => {}}
        onSelectNode={onSelectNode}
      />
    </ConfigProvider>,
  )

  expect(screen.getByText('产业链导航')).toBeInTheDocument()
  expect(screen.getByText('待复核压力 542')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /材料/ }))
  expect(onSelectNode).toHaveBeenCalledWith(nodes[0])
})
