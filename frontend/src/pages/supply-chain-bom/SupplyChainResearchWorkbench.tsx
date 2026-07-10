import { Card, Empty, Flex, Segmented, Space, Tag, Typography } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import type { ChainDeconstructResponse, ChainDeconstructTree, SupplyChainMappingQuality } from '../../api/client'
import CompanyEvidencePanel from './CompanyEvidencePanel'
import SupplyChainCandidateGrid from './SupplyChainCandidateGrid'
import SupplyChainNodeNavigator from './SupplyChainNodeNavigator'
import type { BomNode, CandidateCompany, SelectedNodeThesis, ThemeRow } from './types'

const { Paragraph, Text, Title } = Typography

type ChainTemplateKey =
  | 'default'
  | 'complex_tech'
  | 'ai_compute_infrastructure'
  | 'advanced_packaging_chiplet'
  | 'semiconductor_equipment_materials'
  | 'lithography_equipment_chain'
  | 'data_ai_application_commercialization'
  | 'defense_informatization_unmanned'
  | 'intelligent_driving_v2x'
  | 'controlled_fusion_materials'
  | 'industrial_machine_tools_cnc'
  | 'innovative_drug_cxo_adc_glp1'
  | 'flexible_dc_offshore_wind_grid'
  | 'rare_earth_minor_metals_security'
  | 'display_oled_microled'
  | 'domestic_os_database_industrial_software'
  | 'huawei_ascend_ai_ecosystem'
  | 'offshore_wind_subsea_cable'
  | 'new_power_system_grid'
  | 'embodied_intelligence'
  | 'storage_chips'

interface SupplyChainResearchWorkbenchProps {
  themes: ThemeRow[]
  nodes: BomNode[]
  candidates: CandidateCompany[]
  selectedThemeId?: string
  selectedNodeId?: string
  selectedNodeThesis?: SelectedNodeThesis | null
  mappingQuality?: SupplyChainMappingQuality | null
  chainTemplate?: ChainTemplateKey
  templateResult?: ChainDeconstructResponse | null
  loading?: boolean
  onChainTemplateChange?: (template: ChainTemplateKey) => void
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
  chainTemplate = 'default',
  templateResult,
  loading = false,
  onChainTemplateChange,
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
  const useTemplateView = chainTemplate !== 'default'

  return (
    <section className="supply-chain-workbench" aria-label="产业链拆解工作台">
      <Card>
        <Flex justify="space-between" align="center" gap={16} wrap="wrap">
          <Space direction="vertical" size={2}>
            <Title level={4} style={{ margin: 0 }}>
              产业链拆解工作台
            </Title>
            <Text type="secondary">节点下钻、链路模板、候选横评、证据复核集中处理</Text>
          </Space>
          <Space size={24} wrap>
            <Segmented
              size="small"
              value={chainTemplate}
              options={[
                { label: '通用层级', value: 'default' },
                { label: '复杂科技', value: 'complex_tech' },
                { label: 'AI算力', value: 'ai_compute_infrastructure' },
                { label: '先进封装', value: 'advanced_packaging_chiplet' },
                { label: '设备材料', value: 'semiconductor_equipment_materials' },
                { label: '光刻机', value: 'lithography_equipment_chain' },
                { label: '数据AI', value: 'data_ai_application_commercialization' },
                { label: '军工无人', value: 'defense_informatization_unmanned' },
                { label: '智能驾驶', value: 'intelligent_driving_v2x' },
                { label: '核聚变', value: 'controlled_fusion_materials' },
                { label: '工业母机', value: 'industrial_machine_tools_cnc' },
                { label: '创新药', value: 'innovative_drug_cxo_adc_glp1' },
                { label: '海风柔直', value: 'flexible_dc_offshore_wind_grid' },
                { label: '稀土小金属', value: 'rare_earth_minor_metals_security' },
                { label: '显示', value: 'display_oled_microled' },
                { label: '国产软件', value: 'domestic_os_database_industrial_software' },
                { label: '昇腾', value: 'huawei_ascend_ai_ecosystem' },
                { label: '海风海缆', value: 'offshore_wind_subsea_cable' },
                { label: '新型电力', value: 'new_power_system_grid' },
                { label: '具身智能', value: 'embodied_intelligence' },
                { label: '存储芯片', value: 'storage_chips' },
              ]}
              onChange={(value) => onChainTemplateChange?.(value as ChainTemplateKey)}
            />
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
          {useTemplateView ? (
            <IndustryTemplatePanel templateResult={templateResult} loading={loading} />
          ) : (
            <SupplyChainCandidateGrid
              candidates={scopedCandidates}
              loading={loading}
              selectedCodes={selectedCodes}
              selectedNodeName={selectedNodeThesis?.name}
              mappingMessage={selectedNodeThesis?.mapping_message}
              onToggleCompare={handleToggleCompare}
              onOpenCompany={handleOpenCompany}
            />
          )}
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

function IndustryTemplatePanel({
  templateResult,
  loading,
}: {
  templateResult?: ChainDeconstructResponse | null
  loading?: boolean
}) {
  const layers = useMemo(
    () => (templateResult?.tree?.children || []).filter((layer): layer is ChainDeconstructTree => Boolean(layer?.layer_id)),
    [templateResult],
  )
  const macroContext = templateResult?.macro_context || []

  return (
    <Card
      loading={loading}
      title={templateResult?.template?.name || '复杂科技产业链路模板'}
      extra={<Text type="secondary">{templateResult?.template?.example_theme || 'AI算力'}</Text>}
    >
      {layers.length === 0 ? (
        <Empty description="暂无模板层级" />
      ) : (
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          {macroContext.length > 0 && (
            <div
              style={{
                border: '1px solid rgba(5, 5, 5, 0.08)',
                borderRadius: 8,
                padding: 12,
                background: '#fafafa',
              }}
            >
              <Title level={5} style={{ marginTop: 0 }}>
                宏观环境
              </Title>
              <Space size={[4, 4]} wrap>
                {macroContext.map((item) => (
                  <Tag key={item.region} color="default">
                    {item.region}：{item.policy_stance || 'unknown'} / {item.inflation_state || 'unknown'}
                  </Tag>
                ))}
              </Space>
              <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
                宏观环境只作为流动性和风险偏好背景；缺数据时显示 unknown。
              </Text>
            </div>
          )}
          {layers.map((layer) => (
            <div
              key={layer.node_id}
              style={{
                border: '1px solid rgba(5, 5, 5, 0.08)',
                borderRadius: 8,
                padding: 12,
                background: '#fff',
              }}
            >
              <Flex justify="space-between" align="start" gap={12} wrap="wrap">
                <Space align="center">
                  <Tag color="blue">L{layer.layer_order}</Tag>
                  <Title level={5} style={{ margin: 0 }}>
                    {layer.name}
                  </Title>
                </Space>
              </Flex>
              <Paragraph style={{ margin: '8px 0' }}>{layer.definition}</Paragraph>
              <TemplateField label="环节" items={layer.segments} color="geekblue" />
              <TemplateField label="证据" items={layer.evidence} color="green" />
              <TemplateField label="公司" items={layer.companies} color="gold" />
              <TemplateField label="跟踪指标" items={layer.tracking_metrics} color="purple" />
              <TemplateField label="商业化阶段" items={layer.metrics?.commercialization} color="green" />
              <TemplateField label="预期差指标" items={layer.metrics?.expectation_gap} color="blue" />
              <TemplateField label="启动信号" items={layer.metrics?.trigger_signals} color="orange" />
              <TemplateEvidenceField
                label="CAPEX 证据"
                records={(layer.capex_evidence || []).map((item) => ({
                  key: item.evidence_id,
                  title: item.company || item.evidence_id,
                  tags: [...(item.capex_direction || []), ...(item.mapped_segments || [])],
                  meta: `${item.source_type || 'unknown'} · ${item.evidence_level || 'unknown'} · ${item.as_of_date || 'unknown'}`,
                }))}
              />
              <TemplateEvidenceField
                label="产业物理指标"
                records={(layer.physical_metrics || []).map((item) => ({
                  key: item.metric_id,
                  title: item.name,
                  tags: [item.mapped_segment || '', item.period || '', item.direction || ''].filter(Boolean),
                  meta: `${item.source_type || 'unknown'} · ${item.evidence_level || 'unknown'} · ${item.as_of_date || 'unknown'}`,
                }))}
              />
              <TemplateEvidenceField
                label="证据链摘要"
                records={(layer.evidence_chain || []).map((item) => ({
                  key: item.evidence_id,
                  title: `${item.evidence_type} · ${item.evidence_id}`,
                  tags: [item.mapped_segment || '', item.impact_direction || '', item.confidence || ''].filter(Boolean),
                  meta: `${item.source_type || 'unknown'} · ${item.evidence_level || 'unknown'} · ${item.as_of_date || 'unknown'}`,
                }))}
              />
              {(layer.expectation_gap || layer.trigger_signal) && (
                <div style={{ marginTop: 8 }}>
                  <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>
                    预期差 / 启动追溯
                  </Text>
                  <Space size={[4, 4]} wrap>
                    <Tag color="blue">预期差：{layer.expectation_gap?.gap_direction || 'unknown'}</Tag>
                    <Tag color="blue">强度：{layer.expectation_gap?.gap_strength || 'unknown'}</Tag>
                    <Tag color="orange">启动：{layer.trigger_signal?.signal_strength || 'unknown'}</Tag>
                    <Tag color="default">证据 {layer.expectation_gap?.evidence_ids?.length || 0}</Tag>
                  </Space>
                  {layer.expectation_gap?.calculation_method && (
                    <Text type="secondary" style={{ display: 'block', marginTop: 4 }}>
                      {layer.expectation_gap.calculation_method}
                    </Text>
                  )}
                </div>
              )}
            </div>
          ))}
        </Space>
      )}
    </Card>
  )
}

function TemplateEvidenceField({
  label,
  records,
}: {
  label: string
  records: Array<{ key: string; title: string; tags: string[]; meta: string }>
}) {
  if (records.length === 0) return null
  return (
    <div style={{ marginTop: 8 }}>
      <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>
        {label}
      </Text>
      <Space direction="vertical" size={6} style={{ width: '100%' }}>
        {records.map((record) => (
          <div key={record.key} style={{ borderLeft: '2px solid #d9d9d9', paddingLeft: 8 }}>
            <Text strong>{record.title}</Text>
            <Text type="secondary" style={{ display: 'block' }}>
              {record.meta}
            </Text>
            <Space size={[4, 4]} wrap style={{ marginTop: 4 }}>
              {record.tags.filter(Boolean).slice(0, 6).map((tag) => (
                <Tag key={`${record.key}-${tag}`} color="default">
                  {tag}
                </Tag>
              ))}
            </Space>
          </div>
        ))}
      </Space>
    </div>
  )
}

function TemplateField({
  label,
  items,
  color,
}: {
  label: string
  items?: string[]
  color: string
}) {
  if (!items?.length) return null
  return (
    <div style={{ marginTop: 8 }}>
      <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>
        {label}
      </Text>
      <Space size={[4, 4]} wrap>
        {items.map((item) => (
          <Tag key={`${label}-${item}`} color={color}>
            {item}
          </Tag>
        ))}
      </Space>
    </div>
  )
}
