import { useEffect, useMemo, useState } from 'react'
import { Button, Checkbox, Col, Empty, Input, Row, Space, Statistic, Table, Tag, Tree, Typography } from 'antd'
import { ApartmentOutlined, EyeOutlined, ScanOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import { screenerApi } from '../api/client'
import CandidateCompanyTable from './supply-chain-bom/CandidateCompanyTable'
import CompanyResearchDrawer from './supply-chain-bom/CompanyResearchDrawer'
import NodeThesisPanel from './supply-chain-bom/NodeThesisPanel'
import type {
  BomNode,
  CandidateCompany,
  ResearchIngestionStatus,
  ScoreDimension,
  SelectedNodeThesis,
  SupplyChainDataFreshness,
  ThemeRow,
} from './supply-chain-bom/types'
import { formatNumber } from './supply-chain-bom/formatters'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

interface WorkbenchModel {
  name?: string
  philosophy?: string
  score_dimensions?: ScoreDimension[]
}

function formatChangePct(value?: number) {
  const n = Number(value)
  if (!Number.isFinite(n)) return '--'
  return `${n > 0 ? '+' : ''}${n.toFixed(2)}%`
}

function researchCollectionLabel(status?: string) {
  if (status === 'enabled') return '研报自动采集已启用'
  if (status === 'llm_key_missing') return '研报采集待接入LLM'
  if (status === 'local_catalog_available') return '研报库已接入'
  return '研报源未配置'
}

function researchCollectionColor(status?: string) {
  if (status === 'enabled') return 'green'
  if (status === 'local_catalog_available') return 'blue'
  if (status === 'llm_key_missing') return 'gold'
  return 'orange'
}

export default function SupplyChainBom() {
  const [themes, setThemes] = useState<ThemeRow[]>([])
  const [nodes, setNodes] = useState<BomNode[]>([])
  const [edges, setEdges] = useState<any[]>([])
  const [model, setModel] = useState<WorkbenchModel>({})
  const [candidates, setCandidates] = useState<CandidateCompany[]>([])
  const [nodeCandidates, setNodeCandidates] = useState<CandidateCompany[]>([])
  const [upstreamCandidates, setUpstreamCandidates] = useState<CandidateCompany[]>([])
  const [selectedNodeThesis, setSelectedNodeThesis] = useState<SelectedNodeThesis>({})
  const [dataFreshness, setDataFreshness] = useState<SupplyChainDataFreshness>({})
  const [researchIngestion, setResearchIngestion] = useState<ResearchIngestionStatus>({})
  const [selectedThemeId, setSelectedThemeId] = useState('')
  const [selectedNodeId, setSelectedNodeId] = useState('')
  const [nodeDetail, setNodeDetail] = useState<any>(null)
  const [companyDetail, setCompanyDetail] = useState<CandidateCompany | null>(null)
  const [companyOpen, setCompanyOpen] = useState(false)
  const [extractText, setExtractText] = useState('')
  const [extractResult, setExtractResult] = useState<any>(null)
  const [persistExtraction, setPersistExtraction] = useState(false)
  const [extracting, setExtracting] = useState(false)
  const [loading, setLoading] = useState(false)
  const [candidateLoading, setCandidateLoading] = useState(false)

  const applyWorkbenchPayload = (data: any, replaceCatalog = false) => {
    const nextThemes = data.themes || data.policy_themes || []
    const nextNodes = data.nodes || data.graph_nodes || []
    if (replaceCatalog) {
      setThemes(nextThemes)
      setNodes(nextNodes)
      setEdges(data.edges || data.graph_edges || [])
      setModel(data.model || {})
    }
    setCandidates(data.candidates || [])
    setNodeCandidates(data.node_candidate_companies || [])
    setUpstreamCandidates(data.upstream_influence_candidates || [])
    setSelectedNodeThesis(data.selected_node_thesis || {})
    setDataFreshness(data.data_freshness || {})
    setResearchIngestion(data.research_ingestion || {})
  }

  useEffect(() => {
    let mounted = true
    setLoading(true)
    screenerApi.getSupplyChainWorkbench({ topN: 30 })
      .then(resp => {
        if (!mounted) return
        const data = resp.data || {}
        applyWorkbenchPayload(data, true)
        const nextThemes = data.themes || data.policy_themes || []
        setSelectedThemeId(data.selected_theme_id || nextThemes[0]?.theme_id || '')
        setSelectedNodeId(data.selected_node_id || '')
      })
      .finally(() => {
        if (mounted) setLoading(false)
      })
    return () => {
      mounted = false
    }
  }, [])

  const selectedTheme = useMemo(
    () => themes.find(theme => theme.theme_id === selectedThemeId),
    [themes, selectedThemeId],
  )

  const selectedNode = useMemo(
    () => nodes.find(node => node.node_id === selectedNodeId),
    [nodes, selectedNodeId],
  )

  const filteredNodes = useMemo(() => {
    if (!selectedThemeId) return nodes
    return nodes.filter(node => node.theme_id === selectedThemeId)
  }, [nodes, selectedThemeId])

  const activeCandidates = selectedNodeId ? nodeCandidates : candidates

  const selectTheme = (themeId: string) => {
    setSelectedThemeId(themeId)
    setSelectedNodeId('')
    setNodeDetail(null)
    setNodeCandidates([])
    setSelectedNodeThesis({})
  }

  const selectNode = (node: BomNode) => {
    setSelectedThemeId(node.theme_id)
    setSelectedNodeId(node.node_id)
    setNodeCandidates([])
    setSelectedNodeThesis({})
    setCandidateLoading(true)

    screenerApi.getSupplyChainWorkbench({ topN: 30, nodeId: node.node_id, themeId: node.theme_id })
      .then(resp => applyWorkbenchPayload(resp.data || {}, false))
      .finally(() => setCandidateLoading(false))

    screenerApi.getSupplyChainNode(node.node_id)
      .then(resp => setNodeDetail(resp.data))
      .catch(() => setNodeDetail(null))
  }

  const treeData = useMemo(() => themes.map(theme => ({
    title: theme.name,
    key: theme.theme_id,
    children: nodes
      .filter(node => node.theme_id === theme.theme_id)
      .map(node => ({
        title: `${node.name} · ${node.level}`,
        key: node.node_id,
      })),
  })), [themes, nodes])

  const graphOption = useMemo(() => {
    const graphNodes = filteredNodes.map((node, index) => ({
      id: node.node_id,
      name: node.name,
      value: node.policy_theme,
      symbolSize: selectedNodeId === node.node_id ? 62 : 48,
      x: Math.cos((index / Math.max(1, filteredNodes.length)) * Math.PI * 2) * 180,
      y: Math.sin((index / Math.max(1, filteredNodes.length)) * Math.PI * 2) * 120,
      itemStyle: {
        color: selectedNodeId === node.node_id ? '#d4380d' : index % 3 === 0 ? '#1677ff' : index % 3 === 1 ? '#389e0d' : '#722ed1',
      },
      label: { show: true, formatter: '{b}' },
    }))
    const nodeIds = new Set(graphNodes.map(node => node.id))
    const graphEdges = edges
      .filter(edge => nodeIds.has(edge.from_node_id) && nodeIds.has(edge.to_node_id))
      .map(edge => ({ source: edge.from_node_id, target: edge.to_node_id, name: edge.relation }))
    return {
      tooltip: { trigger: 'item' },
      series: [{
        type: 'graph',
        layout: 'none',
        roam: true,
        data: graphNodes,
        links: graphEdges,
        edgeSymbol: ['none', 'arrow'],
        lineStyle: { color: '#8c8c8c', width: 1.2 },
        label: { color: '#1f1f1f', fontSize: 12 },
      }],
    }
  }, [edges, filteredNodes, selectedNodeId])

  const openCompany = (company: CandidateCompany) => {
    setCompanyDetail(company)
    setCompanyOpen(true)
    screenerApi.getSupplyChainCompany(company.code).then(resp => {
      setCompanyDetail({ ...company, ...resp.data })
    })
  }

  const runExtraction = async () => {
    const text = extractText.trim()
    if (!text) return
    setExtracting(true)
    try {
      const resp = await screenerApi.extractSupplyChainFacts(text, { source_type: 'manual_paste' }, persistExtraction)
      setExtractResult(resp.data)
    } finally {
      setExtracting(false)
    }
  }

  const themeColumns: any[] = [
    {
      title: '政策主题',
      dataIndex: 'name',
      render: (_: string, row: ThemeRow) => (
        <Button type="link" icon={<ApartmentOutlined />} onClick={() => selectTheme(row.theme_id)}>
          {row.name}
        </Button>
      ),
    },
    { title: '权重', dataIndex: 'policy_weight', width: 76, render: (v: number) => formatNumber(v, 2) },
    { title: '节点', dataIndex: 'node_count', width: 68 },
  ]

  const nodeColumns: any[] = [
    {
      title: 'BOM节点',
      dataIndex: 'name',
      render: (_: string, row: BomNode) => (
        <Button type="link" icon={<EyeOutlined />} onClick={() => selectNode(row)}>
          {row.name}
        </Button>
      ),
    },
    { title: '层级', dataIndex: 'level', width: 86, render: (v: string) => <Tag>{v}</Tag> },
    { title: '类型', dataIndex: 'node_type', width: 94 },
  ]

  const upstreamColumns: any[] = [
    {
      title: '上游公司',
      width: 180,
      render: (_: unknown, row: CandidateCompany) => (
        <Button type="link" icon={<EyeOutlined />} onClick={() => openCompany(row)}>
          {row.name || row.code}
          <Text type="secondary" style={{ marginLeft: 6 }}>{row.code}</Text>
        </Button>
      ),
    },
    {
      title: '所属行业/行情',
      width: 190,
      render: (_: unknown, row: CandidateCompany) => (
        <Space direction="vertical" size={4}>
          <Space wrap>
            <Tag>{row.industry || '行业待确认'}</Tag>
            <Tag color="gold">{row.pool_status || '观察池'}</Tag>
          </Space>
          <Space size={6}>
            <Text strong>{formatNumber(row.last_price, 2)}</Text>
            <Tag color={Number(row.last_change_pct) >= 0 ? 'red' : 'green'}>{formatChangePct(row.last_change_pct)}</Tag>
            <Text type="secondary">{row.last_trade_date || '--'}</Text>
          </Space>
        </Space>
      ),
    },
    {
      title: '上游影响路径',
      width: 320,
      render: (_: unknown, row: CandidateCompany) => (
        <Space direction="vertical" size={4}>
          <Space wrap>
            <Tag color="cyan">{row.upstream_node || row.layer || '上游节点'}</Tag>
            <Tag color="blue">{row.impact_role || '上游使能环节'}</Tag>
          </Space>
          {(row.influence_paths || []).slice(0, 2).map(path => <Text key={path}>{path}</Text>)}
        </Space>
      ),
    },
    {
      title: '影响的下游产业',
      width: 240,
      render: (_: unknown, row: CandidateCompany) => (
        <Space wrap>
          {(row.downstream_chains || []).map(chain => <Tag key={chain} color="processing">{chain}</Tag>)}
        </Space>
      ),
    },
    {
      title: '待验证证据',
      width: 280,
      render: (_: unknown, row: CandidateCompany) => (
        <Space wrap>
          {(row.evidence_gaps || []).slice(0, 3).map(gap => <Tag key={gap}>{gap}</Tag>)}
        </Space>
      ),
    },
    {
      title: '入池理由',
      dataIndex: 'selection_reason',
      render: (reason: string) => <Text>{reason || '等待产品、客户、量产与财务证据补强'}</Text>,
    },
  ]

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>产业链拆解</Title>
          <Text type="secondary">{model.name || '大葱产业链解构选股模型 V4'}</Text>
        </div>
        <Space wrap>
          <Tag color="blue">BOM V4</Tag>
          <Tag color="green">{selectedTheme?.name || selectedNode?.policy_theme || '政策主题'}</Tag>
          <Tag color="gold">候选 {activeCandidates.length}</Tag>
          {!!upstreamCandidates.length && <Tag color="cyan">上游观察 {upstreamCandidates.length}</Tag>}
          {dataFreshness.market?.latest_trade_date && (
            <Tag color="red">行情更新至 {dataFreshness.market.latest_trade_date}</Tag>
          )}
          {dataFreshness.research_reports?.latest_pub_date && (
            <Tag color="purple">研报更新至 {dataFreshness.research_reports.latest_pub_date}</Tag>
          )}
          {dataFreshness.broker_recommend?.latest_month && (
            <Tag>券商评级 {dataFreshness.broker_recommend.latest_month}</Tag>
          )}
        </Space>
      </div>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={7}>
          <div style={{ border: '1px solid #f0f0f0', borderRadius: 8, background: '#fff', padding: 12, minHeight: 360 }}>
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <Title level={5} style={{ margin: 0 }}>BOM层层拆解</Title>
              {treeData.length ? (
                <Tree
                  selectedKeys={[selectedNodeId || selectedThemeId]}
                  defaultExpandAll
                  treeData={treeData}
                  onSelect={keys => {
                    const key = String(keys[0] || '')
                    if (themes.some(theme => theme.theme_id === key)) {
                      selectTheme(key)
                      return
                    }
                    const nextNode = nodes.find(node => node.node_id === key)
                    if (nextNode) selectNode(nextNode)
                  }}
                />
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无BOM节点" />
              )}
              <Table
                loading={loading}
                rowKey="theme_id"
                size="small"
                columns={themeColumns}
                dataSource={themes}
                pagination={false}
                rowClassName={row => row.theme_id === selectedThemeId ? 'ant-table-row-selected' : ''}
              />
            </Space>
          </div>
        </Col>

        <Col xs={24} lg={10}>
          <div style={{ height: 360, border: '1px solid #f0f0f0', borderRadius: 8, background: '#fff' }}>
            <ReactECharts
              option={graphOption}
              style={{ height: 358 }}
              onEvents={{
                click: (params: any) => {
                  const nextNode = nodes.find(node => node.node_id === params?.data?.id)
                  if (nextNode) selectNode(nextNode)
                },
              }}
            />
          </div>
        </Col>

        <Col xs={24} lg={7}>
          <div style={{ border: '1px solid #f0f0f0', borderRadius: 8, background: '#fff', padding: 16, minHeight: 360 }}>
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <Title level={5} style={{ margin: 0 }}>选股模型</Title>
              <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                {model.philosophy || '政策主题定方向，BOM拆解定环节，候选公司池定标的，共振信息定研究信号。'}
              </Paragraph>
              {selectedTheme?.interpretation && (
                <Paragraph style={{ marginBottom: 0 }}>
                  {selectedTheme.interpretation}
                </Paragraph>
              )}
              {selectedTheme?.strategic_logic && (
                <Text type="secondary">{selectedTheme.strategic_logic}</Text>
              )}
              {!!selectedTheme?.bom_focus?.length && (
                <Space wrap>
                  {selectedTheme.bom_focus.map(item => <Tag key={item} color="cyan">{item}</Tag>)}
                </Space>
              )}
              {!!selectedTheme?.evidence_focus?.length && (
                <Space wrap>
                  {selectedTheme.evidence_focus.map(item => <Tag key={item}>{item}</Tag>)}
                </Space>
              )}
              <Row gutter={12}>
                <Col span={8}><Statistic title="候选公司" value={activeCandidates.length} /></Col>
                <Col span={8}><Statistic title="BOM节点" value={nodes.length} /></Col>
                <Col span={8}><Statistic title="证据" value={nodeDetail?.evidence?.length || 0} /></Col>
              </Row>
              <Space wrap>
                {(model.score_dimensions || []).map(item => (
                  <Tag key={item.key} color={item.key === 'commercialization' ? 'green' : 'processing'}>
                    <span>{item.name}</span>
                    <Text style={{ marginLeft: 4 }}>{item.weight}</Text>
                  </Tag>
                ))}
              </Space>
            </Space>
          </div>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} xl={14}>
          <Table
            rowKey="node_id"
            size="small"
            columns={nodeColumns}
            dataSource={filteredNodes}
            pagination={{ pageSize: 8, showSizeChanger: false }}
          />
        </Col>
        <Col xs={24} xl={10}>
          <div style={{ minHeight: 276, border: '1px solid #f0f0f0', borderRadius: 8, background: '#fff', padding: 16 }}>
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <Text strong>当前节点研究上下文</Text>
              <NodeThesisPanel
                node={selectedNode}
                thesis={selectedNodeThesis}
                candidateCount={nodeCandidates.length}
                evidenceCount={nodeDetail?.evidence?.length || 0}
                policyWeight={selectedTheme?.policy_weight || 1}
              />
            </Space>
          </div>
        </Col>
      </Row>

      <div style={{ marginTop: 16 }}>
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Space align="center" style={{ justifyContent: 'space-between', width: '100%' }}>
            <Title level={5} style={{ margin: 0 }}>候选公司池</Title>
            <Text type="secondary">
              {selectedNode ? `${selectedNode.name}节点候选公司，基于BOM映射、商业阶段、政策力度、业绩与市场共振排序` : '全局候选池，选择BOM节点后切换为节点公司池'}
            </Text>
          </Space>
          <CandidateCompanyTable
            candidates={activeCandidates}
            loading={candidateLoading}
            selectedNodeName={selectedNode?.name}
            mappingMessage={selectedNodeThesis.mapping_message}
            onOpenCompany={openCompany}
          />
        </Space>
      </div>

      <div style={{ marginTop: 16 }}>
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Space align="center" style={{ justifyContent: 'space-between', width: '100%' }}>
            <Space wrap>
              <Title level={5} style={{ margin: 0 }}>上游影响观察池</Title>
              <Tag color="cyan">{upstreamCandidates.length}</Tag>
            </Space>
            <Text type="secondary">从下游战略产业反向拆解上游材料、设备、工艺、软件与零部件，不再用公司所属行业做硬边界</Text>
          </Space>
          <Table
            rowKey="code"
            size="small"
            columns={upstreamColumns}
            dataSource={upstreamCandidates}
            pagination={{ pageSize: 6, showSizeChanger: false }}
            scroll={{ x: 1320 }}
            locale={{
              emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无上游影响观察候选" />,
            }}
          />
        </Space>
      </div>

      <div style={{ marginTop: 16, border: '1px solid #f0f0f0', borderRadius: 8, background: '#fff', padding: 16 }}>
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Space wrap>
            <Text strong>LLM图谱抽取</Text>
            <Tag color={researchCollectionColor(researchIngestion.auto_collection_status)}>
              {researchCollectionLabel(researchIngestion.auto_collection_status)}
            </Tag>
            <Tag color={researchIngestion.llm_auto_extract_enabled ? 'green' : 'default'}>
              {researchIngestion.llm_auto_extract_enabled ? 'LLM自动抽取已开启' : 'LLM自动抽取未开启'}
            </Tag>
            {researchIngestion.batch_extract_endpoint && <Tag color="processing">研报批量入口已就绪</Tag>}
            {!!researchIngestion.source_row_count && (
              <Tag>{researchIngestion.source_row_count}篇研报</Tag>
            )}
            {extractResult?.status && <Tag color={extractResult.status === 'ok' ? 'green' : 'orange'}>{extractResult.status}</Tag>}
            {extractResult?.reason && <Text type="secondary">{extractResult.reason}</Text>}
          </Space>
          {researchIngestion.message && (
            <Text type="secondary">{researchIngestion.message}</Text>
          )}
          <TextArea
            value={extractText}
            onChange={e => setExtractText(e.target.value)}
            placeholder="粘贴政策、公告、研报文本"
            autoSize={{ minRows: 3, maxRows: 6 }}
          />
          <Space wrap>
            <Button type="primary" icon={<ScanOutlined />} loading={extracting} disabled={!extractText.trim()} onClick={runExtraction}>
              抽取图谱
            </Button>
            <Checkbox checked={persistExtraction} onChange={e => setPersistExtraction(e.target.checked)}>
              写入待审核图谱
            </Checkbox>
            {extractResult?.policy_theme && <Tag color="blue">{extractResult.policy_theme}</Tag>}
            {extractResult?.commercialization_stage && <Tag>{extractResult.commercialization_stage}</Tag>}
            {extractResult?.persisted && <Tag color="green">已写入</Tag>}
          </Space>
          {extractResult?.records && (
            <Space wrap>
              <Tag color="processing">映射 {extractResult.records.mappings?.length || 0}</Tag>
              <Tag color="processing">证据 {extractResult.records.evidence?.length || 0}</Tag>
            </Space>
          )}
          {!!extractResult?.bom_nodes?.length && (
            <Space wrap>
              {extractResult.bom_nodes.map((node: string) => <Tag key={node}>{node}</Tag>)}
            </Space>
          )}
        </Space>
      </div>

      <CompanyResearchDrawer
        open={companyOpen}
        company={companyDetail}
        onClose={() => setCompanyOpen(false)}
      />
    </div>
  )
}
