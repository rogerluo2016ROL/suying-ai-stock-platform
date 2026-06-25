import { Card, Empty, Flex, Space, Statistic, Typography } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import type { SupplyChainMappingQuality } from '../../api/client'
import CompanyEvidencePanel from './CompanyEvidencePanel'
import SupplyChainCandidateGrid from './SupplyChainCandidateGrid'
import SupplyChainNodeNavigator from './SupplyChainNodeNavigator'
import type { BomNode, CandidateCompany, SelectedNodeThesis, ThemeRow } from './types'

const { Text, Title } = Typography

interface SupplyChainResearchWorkbenchProps {
  themes: ThemeRow[]
  nodes: BomNode[]
  candidates: CandidateCompany[]
  selectedThemeId?: string
  selectedNodeId?: string
  selectedNodeThesis?: SelectedNodeThesis | null
  mappingQuality?: SupplyChainMappingQuality | null
  loading?: boolean
  onSelectTheme?: (themeId: string) => void
  onSelectNode?: (nodeId: string) => void
  onOpenCompany?: (company: CandidateCompany) => void
  onReviewMapping?: (code: string, nodeId: string, decision: string) => Promise<void> | void
}

const filterCandidatesByNode = (candidates: CandidateCompany[], selectedNodeId?: string) => {
  if (!selectedNodeId) {
    return candidates
  }
  const filtered = candidates.filter((candidate) => candidate.node_id === selectedNodeId)
  return filtered.length > 0 ? filtered : candidates
}

export default function SupplyChainResearchWorkbench({
  themes,
  nodes,
  candidates,
  selectedThemeId,
  selectedNodeId,
  selectedNodeThesis,
  mappingQuality,
  loading = false,
  onSelectTheme,
  onSelectNode,
  onOpenCompany,
  onReviewMapping,
}: SupplyChainResearchWorkbenchProps) {
  const scopedCandidates = useMemo(
    () => filterCandidatesByNode(candidates, selectedNodeId),
    [candidates, selectedNodeId],
  )
  const [selectedCompany, setSelectedCompany] = useState<CandidateCompany | null>(scopedCandidates[0] || null)
  const [selectedCodes, setSelectedCodes] = useState<string[]>([])

  useEffect(() => {
    if (scopedCandidates.length === 0) {
      setSelectedCompany(null)
      return
    }
    if (!selectedCompany || !scopedCandidates.some((candidate) => candidate.code === selectedCompany.code)) {
      setSelectedCompany(scopedCandidates[0])
    }
  }, [scopedCandidates, selectedCompany])

  const handleOpenCompany = (company: CandidateCompany) => {
    setSelectedCompany(company)
    onOpenCompany?.(company)
  }

  const handleToggleCompare = (company: CandidateCompany) => {
    setSelectedCodes((codes) => (
      codes.includes(company.code)
        ? codes.filter((code) => code !== company.code)
        : [...codes, company.code]
    ))
  }

  const handleSelectNode = (node: BomNode) => {
    onSelectNode?.(node.node_id)
  }

  const reviewCompany = selectedCompany || scopedCandidates[0] || null
  const evidenceCount = reviewCompany?.moat_evidence?.length || reviewCompany?.evidence?.length || 0

  return (
    <section className="supply-chain-workbench" aria-label="产业链拆解工作台">
      <Card>
        <Flex justify="space-between" align="center" gap={16} wrap="wrap">
          <Space direction="vertical" size={2}>
            <Title level={4} style={{ margin: 0 }}>
              产业链拆解工作台
            </Title>
            <Text type="secondary">节点下钻、候选横评、证据复核集中处理</Text>
          </Space>
          <Space size={24}>
            <Statistic title="主题" value={themes.length} />
            <Statistic title="节点" value={nodes.length} />
            <Statistic title="候选" value={candidates.length} />
            <Statistic title="待复核" value={mappingQuality?.review_queue_count || 0} />
          </Space>
        </Flex>
      </Card>

      <div className="supply-chain-workbench-grid">
        <div className="supply-chain-workbench-panel supply-chain-workbench-panel--nav">
          <SupplyChainNodeNavigator
            themes={themes}
            nodes={nodes}
            selectedThemeId={selectedThemeId || ''}
            selectedNodeId={selectedNodeId || ''}
            quality={mappingQuality}
            selectedNodeThesis={selectedNodeThesis || {}}
            candidateCount={scopedCandidates.length}
            evidenceCount={evidenceCount}
            onSelectTheme={(themeId) => onSelectTheme?.(themeId)}
            onSelectNode={handleSelectNode}
          />
        </div>

        <div className="supply-chain-workbench-panel supply-chain-workbench-panel--candidates">
          <SupplyChainCandidateGrid
            candidates={scopedCandidates}
            loading={loading}
            selectedCodes={selectedCodes}
            selectedNodeName={selectedNodeThesis?.name}
            mappingMessage={selectedNodeThesis?.mapping_message}
            onToggleCompare={handleToggleCompare}
            onOpenCompany={handleOpenCompany}
          />
        </div>

        <div className="supply-chain-workbench-panel supply-chain-workbench-panel--evidence">
          {candidates.length === 0 ? (
            <Card>
              <Empty description="暂无候选公司" />
            </Card>
          ) : (
            <CompanyEvidencePanel company={reviewCompany} onReview={onReviewMapping} />
          )}
        </div>
      </div>
    </section>
  )
}
