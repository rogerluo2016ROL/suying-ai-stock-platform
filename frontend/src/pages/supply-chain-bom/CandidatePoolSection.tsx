// 候选公司池区块：筛选条 + 三因子气泡图 + 候选表
// 从 SupplyChainBom.tsx 拆出，showBubbleChart / V6 筛选候选 UI 状态下沉；
// fallbackCandidates 为 workbench 候选（筛选器无结果时回退展示）

import { useCallback, useMemo, useState } from 'react'
import { Checkbox, Col, Row, Space, Tag, Typography } from 'antd'
import type { ChainCandidate, FilterSummary, ResonanceSummary } from '../../api/client'
import CandidateFilterBar from './CandidateFilterBar'
import ChainBubbleChart from './ChainBubbleChart'
import CandidateCompanyTable from './CandidateCompanyTable'
import { chainCandidateToCandidateCompany, type BomNode, type CandidateCompany } from './types'

const { Title, Text } = Typography

interface CandidatePoolSectionProps {
  fallbackCandidates: CandidateCompany[]
  workbenchLoading: boolean
  selectedNode?: BomNode
  mappingMessage?: string
  themeName?: string
  onOpenCompany: (company: CandidateCompany) => void
}

export default function CandidatePoolSection({
  fallbackCandidates,
  workbenchLoading,
  selectedNode,
  mappingMessage,
  themeName,
  onOpenCompany,
}: CandidatePoolSectionProps) {
  const [showBubbleChart, setShowBubbleChart] = useState(true)

  // Phase 3: V6 chain candidates state (from CandidateFilterBar)
  const [chainCandidates, setChainCandidates] = useState<CandidateCompany[]>([])
  const [chainCandidateLoading, setChainCandidateLoading] = useState(false)
  const [filterSummary, setFilterSummary] = useState<FilterSummary | null>(null)
  const [resonanceSummary, setResonanceSummary] = useState<ResonanceSummary | null>(null)

  // Phase 3: Handler for CandidateFilterBar candidates change
  const handleChainCandidatesChange = useCallback((candidates: ChainCandidate[]) => {
    // Convert ChainCandidate[] to CandidateCompany[] for compatibility
    const convertedCandidates = candidates.map(chainCandidateToCandidateCompany)
    setChainCandidates(convertedCandidates)
  }, [])

  // Phase 3: Handler for CandidateFilterBar loading state
  const handleChainCandidateLoadingChange = useCallback((loading: boolean) => {
    setChainCandidateLoading(loading)
  }, [])

  // Phase 3: Handler for CandidateFilterBar summary change
  const handleSummaryChange = useCallback((filterSum: FilterSummary, resonanceSum: ResonanceSummary) => {
    setFilterSummary(filterSum)
    setResonanceSummary(resonanceSum)
  }, [])

  // Phase 3: Determine which candidates to display (chain candidates or workbench candidates)
  const candidates = useMemo(() => {
    // When chainCandidates has data, use it; otherwise use workbench candidates
    return chainCandidates.length > 0 ? chainCandidates : fallbackCandidates
  }, [chainCandidates, fallbackCandidates])

  const loading = workbenchLoading || chainCandidateLoading

  return (
    <div style={{ marginTop: 16 }}>
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Space align="center" style={{ justifyContent: 'space-between', width: '100%' }}>
          <Space wrap>
            <Title level={5} style={{ margin: 0 }}>候选公司池</Title>
            <Tag color="blue">{candidates.length} 候选</Tag>
            {filterSummary && <Tag color="green">筛选生效</Tag>}
            {resonanceSummary && (
              <Space size={4}>
                {resonanceSummary['强启动'] > 0 && <Tag color="red">强启动 {resonanceSummary['强启动']}</Tag>}
                {resonanceSummary['启动'] > 0 && <Tag color="orange">启动 {resonanceSummary['启动']}</Tag>}
              </Space>
            )}
          </Space>
          <Checkbox
            checked={showBubbleChart}
            onChange={e => setShowBubbleChart(e.target.checked)}
          >
            显示气泡图
          </Checkbox>
        </Space>
        <Text type="secondary">
          {selectedNode ? `${selectedNode.name}节点候选公司，基于BOM映射、商业阶段、政策力度、业绩与市场共振排序` : '全局候选池，使用筛选器按三因子共振过滤'}
        </Text>

        {/* Phase 3: CandidateFilterBar for V6 resonance filtering */}
        <CandidateFilterBar
          onCandidatesChange={handleChainCandidatesChange}
          onLoadingChange={handleChainCandidateLoadingChange}
          onSummaryChange={handleSummaryChange}
          topN={50}
          disabled={false}
        />

        {/* Phase 3: ChainBubbleChart for three-factor resonance visualization */}
        {showBubbleChart && (
          <Row gutter={[16, 16]}>
            <Col xs={24} lg={12}>
              <ChainBubbleChart
                candidates={candidates}
                loading={loading}
                onPointClick={onOpenCompany}
                themeName={themeName}
                style={{ height: 420 }}
              />
            </Col>
            <Col xs={24} lg={12}>
              <CandidateCompanyTable
                candidates={candidates}
                loading={loading}
                selectedNodeName={selectedNode?.name}
                mappingMessage={mappingMessage}
                onOpenCompany={onOpenCompany}
              />
            </Col>
          </Row>
        )}

        {/* Show table only when bubble chart is hidden */}
        {!showBubbleChart && (
          <CandidateCompanyTable
            candidates={candidates}
            loading={loading}
            selectedNodeName={selectedNode?.name}
            mappingMessage={mappingMessage}
            onOpenCompany={onOpenCompany}
          />
        )}
      </Space>
    </div>
  )
}
