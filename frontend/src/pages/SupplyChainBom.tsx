import { useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, Button, Checkbox, Col, Empty, Input, message, Row, Space, Statistic, Table, Tag, Typography } from 'antd'
import { ApartmentOutlined, EyeOutlined, FileTextOutlined, ScanOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import { useLocation, useNavigate } from 'react-router-dom'
import { screenerApi, chainApi, type PolicyInterpretResponse, type ChainDeconstructResponse, type ChainNode, type ChainCandidate, type FilterSummary, type ResonanceSummary, type SupplyChainMappingQuality, type SupplyChainMappingReviewDecision } from '../api/client'
import type { SupplyChainTheme, SupplyChainNode } from '../api/types'
import { DataFreshnessBar, MetricCard, PrototypePage, PrototypePageHeader, PrototypeTabs } from '../components/prototype'
import CandidateCompanyTable from './supply-chain-bom/CandidateCompanyTable'
import CompanyResearchDrawer from './supply-chain-bom/CompanyResearchDrawer'
import NodeThesisPanel from './supply-chain-bom/NodeThesisPanel'
import ChainTreeChart from './supply-chain-bom/ChainTreeChart'
import MethodSelector, { type ChainMethod } from './supply-chain-bom/MethodSelector'
import CandidateFilterBar from './supply-chain-bom/CandidateFilterBar'
import ChainBubbleChart from './supply-chain-bom/ChainBubbleChart'
import SupplyChainMappingReviewPanel from './supply-chain-bom/SupplyChainMappingReviewPanel'
import SupplyChainResearchWorkbench from './supply-chain-bom/SupplyChainResearchWorkbench'
import type {
  BomNode,
  CandidateCompany,
  ResearchIngestionStatus,
  ScoreDimension,
  SelectedNodeThesis,
  SupplyChainDataFreshness,
  ThemeRow,
} from './supply-chain-bom/types'
import { chainCandidateToCandidateCompany } from './supply-chain-bom/types'
import { formatNumber } from './supply-chain-bom/formatters'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

const supplyChainTabs = [
  { key: 'policy', path: '/supply-chain-bom/policy', label: '政策梳理', subLabel: '政策证据' },
  { key: 'chain', path: '/supply-chain-bom', label: '产业链解构', subLabel: '三种模式' },
  { key: 'company', path: '/supply-chain-bom/company', label: '多维度分析', subLabel: '公司对比' },
]

function activeSupplyChainTab(pathname: string) {
  if (pathname.startsWith('/supply-chain-bom/policy')) return 'policy'
  if (pathname.startsWith('/supply-chain-bom/company')) return 'company'
  return 'chain'
}

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
  if (status === 'llm_key_missing') return '等待研报智能解读授权'
  if (status === 'local_catalog_available') return '研报库已接入'
  return '研报源未配置'
}

function researchCollectionColor(status?: string) {
  if (status === 'enabled') return 'green'
  if (status === 'local_catalog_available') return 'blue'
  if (status === 'llm_key_missing') return 'gold'
  return 'orange'
}

function endpointStatus(error: unknown) {
  return (error as { response?: { status?: number } })?.response?.status
}

function mappingQualityErrorText(error: unknown) {
  const status = endpointStatus(error)
  if (status === 404) {
    return '当前服务未暴露 /api/v1/screener/supply-chain/mapping-review/quality，请重建或更新 screener-service；图谱和候选池仍可继续查看。'
  }
  return '映射质量报告加载失败，请检查 screener-service 和网关状态。'
}

function chainDeconstructErrorText(error: unknown) {
  const status = endpointStatus(error)
  if (status === 500) return '拆解接口返回 500，当前图谱可能是旧数据或默认目录。请检查 screener-service 后重试。'
  if (status === 404) return '拆解接口不存在，当前图谱可能来自默认目录。请确认后端路由是否启用。'
  return '拆解接口连接异常，当前图谱可能是旧数据或默认目录。'
}

function chainMethodSummary(method: ChainMethod) {
  if (method === 'value_chain') {
    return {
      title: '价值链拆解',
      desc: '按原材料、核心零部件、制造设备、封装测试拆分利润池，突出毛利率、议价权和国产替代空间。',
      stats: [
        ['最高毛利环节', '核心零部件 45%'],
        ['利润弹性', '制造设备 38%'],
        ['短板约束', '封装测试 18%'],
      ],
    }
  }
  if (method === 'competition') {
    return {
      title: '竞争格局',
      desc: '按市场份额、技术壁垒、市值体量和客户绑定关系评估公司位置，区分龙头、跟随者和卡位标的。',
      stats: [
        ['龙头份额', 'ASML 80%'],
        ['国产替代', '中微公司 15%'],
        ['技术壁垒', '光刻/刻蚀高'],
      ],
    }
  }
  return {
    title: '上下游拆解',
    desc: '从政策主题向上游材料、核心部件、制造设备、下游应用逐层展开，定位可跟踪节点和映射公司。',
    stats: [
      ['上游节点', '硅片/光刻胶'],
      ['核心节点', '光源/物镜'],
      ['下游应用', '晶圆厂/设备商'],
    ],
  }
}

// Convert ChainNode from API to BomNode for display
function chainNodeToBomNode(node: ChainNode, themeId: string): BomNode {
  return {
    node_id: node.node_id,
    theme_id: themeId,
    chain_id: themeId,
    parent_node_id: undefined,
    child_node_ids: node.children?.map(c => c.node_id) || [],
    level: `L${node.layer}`,
    name: node.name,
    node_type: 'chain_node',
    keywords: [],
    policy_theme: undefined,
  }
}

// Recursively flatten ChainNode tree to BomNode array
function flattenChainNodes(node: ChainNode, themeId: string, result: BomNode[] = []): BomNode[] {
  result.push(chainNodeToBomNode(node, themeId))
  if (node.children) {
    for (const child of node.children) {
      flattenChainNodes(child, themeId, result)
    }
  }
  return result
}

export default function SupplyChainBom() {
  const location = useLocation()
  const navigate = useNavigate()
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
  const [loading, setLoading] = useState(false)
  const [candidateLoading, setCandidateLoading] = useState(false)
  const [mappingQuality, setMappingQuality] = useState<SupplyChainMappingQuality | null>(null)

  // P2-08: Policy interpretation state (replaces LLM extraction)
  const [policyText, setPolicyText] = useState('')
  const [policyResult, setPolicyResult] = useState<PolicyInterpretResponse | null>(null)
  const [policyLoading, setPolicyLoading] = useState(false)
  const [persistPolicy, setPersistPolicy] = useState(false)

  // P2-08: Chain method selector state
  const [chainMethod, setChainMethod] = useState<ChainMethod>('upstream_downstream')
  const [chainDeconstructResult, setChainDeconstructResult] = useState<ChainDeconstructResponse | null>(null)
  const [chainLoading, setChainLoading] = useState(false)
  const [chainDeconstructError, setChainDeconstructError] = useState('')

  // Phase 3: V6 chain candidates state (from CandidateFilterBar)
  const [chainCandidates, setChainCandidates] = useState<CandidateCompany[]>([])
  const [chainCandidateLoading, setChainCandidateLoading] = useState(false)
  const [filterSummary, setFilterSummary] = useState<FilterSummary | null>(null)
  const [resonanceSummary, setResonanceSummary] = useState<ResonanceSummary | null>(null)
  const [showBubbleChart, setShowBubbleChart] = useState(true)
  const [mappingQualityError, setMappingQualityError] = useState('')

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

  const refreshMappingQuality = () => {
    setMappingQualityError('')
    screenerApi.getSupplyChainMappingQuality()
      .then(resp => setMappingQuality(resp.data))
      .catch((err) => {
        setMappingQuality(null)
        setMappingQualityError(mappingQualityErrorText(err))
      })
  }

  useEffect(() => {
    let mounted = true
    setLoading(true)
    screenerApi.getSupplyChainWorkbench({ topN: 30 })
      .then(resp => {
        if (!mounted) return
        const data = resp.data || {}
        applyWorkbenchPayload(data, true)
        const nextThemes = (data as unknown as { themes?: (SupplyChainTheme & { theme_id?: string })[]; policy_themes?: (SupplyChainTheme & { theme_id?: string })[] }).themes || (data as unknown as { policy_themes?: (SupplyChainTheme & { theme_id?: string })[] }).policy_themes || []
        const firstTheme = nextThemes[0]
        setSelectedThemeId((data as unknown as { selected_theme_id?: string }).selected_theme_id || firstTheme?.id || firstTheme?.theme_id || '')
        setSelectedNodeId((data as unknown as { selected_node_id?: string }).selected_node_id || '')
      })
      .finally(() => {
        if (mounted) setLoading(false)
      })
    refreshMappingQuality()
    return () => {
      mounted = false
    }
  }, [])

  // P2-08: Fetch chain deconstruct when method changes and theme is selected
  useEffect(() => {
    if (!selectedThemeId) return
    let mounted = true
    setChainLoading(true)
    setChainDeconstructError('')
    chainApi.deconstructChain({ theme_id: selectedThemeId, method: chainMethod })
      .then(resp => {
        if (!mounted) return
        const data = resp.data as ChainDeconstructResponse
        setChainDeconstructResult(data)
        setChainDeconstructError('')
        // Convert chain nodes to BomNodes for display
        if (data.tree) {
          const bomNodes = flattenChainNodes(data.tree as SupplyChainNode, selectedThemeId)
          setNodes(bomNodes)
        }
      })
      .catch(err => {
        if (!mounted) return
        console.error('Chain deconstruct failed:', err)
        setChainDeconstructError(chainDeconstructErrorText(err))
        message.warning('产业链拆解加载失败，使用默认数据')
      })
      .finally(() => {
        if (mounted) setChainLoading(false)
      })
    return () => {
      mounted = false
    }
  }, [selectedThemeId, chainMethod])

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
  const methodSummary = useMemo(() => chainMethodSummary(chainMethod), [chainMethod])
  const activeModuleKey = activeSupplyChainTab(location.pathname)
  const activeModuleTab = supplyChainTabs.find(tab => tab.key === activeModuleKey) || supplyChainTabs[1]

  const selectTheme = (themeId: string) => {
    setSelectedThemeId(themeId)
    setSelectedNodeId('')
    setNodeDetail(null)
    setNodeCandidates([])
    setSelectedNodeThesis({})
    setChainDeconstructResult(null)
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

  const selectNodeById = (nodeId: string) => {
    const node = nodes.find(item => item.node_id === nodeId)
    if (node) {
      selectNode(node)
    }
  }

  const reviewMapping = async (code: string, nodeId: string, decision: string) => {
    const reviewDecision = decision as SupplyChainMappingReviewDecision['decision']
    await screenerApi.reviewSupplyChainMapping(code, nodeId, { decision: reviewDecision })
    const nextStatus = reviewDecision === 'needs_more_evidence' ? 'weak_evidence' : reviewDecision
    const updateMappingStatus = (items: CandidateCompany[]) => items.map(item => (
      item.code === code && item.node_id === nodeId
        ? { ...item, mapping_status: nextStatus }
        : item
    ))
    setCandidates(updateMappingStatus)
    setNodeCandidates(updateMappingStatus)
    refreshMappingQuality()
    message.success('映射复核已提交')
  }

  // P2-08: Policy interpretation handler (replaces LLM extraction)
  const runPolicyInterpret = async () => {
    const text = policyText.trim()
    if (!text) {
      message.warning('请输入政策解读文本')
      return
    }
    setPolicyLoading(true)
    try {
      const resp = await chainApi.interpretPolicy(text, { source_type: 'manual_paste' }, persistPolicy)
      const data = resp.data as PolicyInterpretResponse
      setPolicyResult(data)
      if (data.status === 'ok') {
        message.success('政策解读完成')
        // If interpretation extracted themes, add them to the list
        if (data.interpretation_result?.industry_themes?.length) {
          const newThemes = data.interpretation_result.industry_themes.map((t: any, idx: number) => ({
            theme_id: t.id || `policy-${Date.now()}-${idx}`,
            name: t.name || '新政策主题',
            policy_weight: t.weight || 1,
            keywords: t.keywords || [],
            node_count: 0,
          }))
          setThemes(prev => [...prev, ...newThemes])
        }
      } else if (data.status === 'disabled') {
        message.info(data.reason || '政策解读功能未启用')
      } else {
        message.error(data.reason || '政策解读失败')
      }
    } catch (err) {
      console.error('Policy interpret failed:', err)
      message.error('政策解读请求失败')
    } finally {
      setPolicyLoading(false)
    }
  }

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
  const displayCandidates = useMemo(() => {
    // When chainCandidates has data, use it; otherwise use workbench candidates
    return chainCandidates.length > 0 ? chainCandidates : activeCandidates
  }, [chainCandidates, activeCandidates])

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
      setCompanyDetail({ ...company, ...(resp.data as unknown as Record<string, unknown>) })
    })
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
    <PrototypePage className="supply-chain-prototype">
      <PrototypeTabs
        ariaLabel="产业链拆解页签"
        activeKey={activeModuleKey}
        onChange={(key) => {
          const tab = supplyChainTabs.find(item => item.key === key)
          if (tab) navigate(tab.path)
        }}
        items={supplyChainTabs.map((tab, index) => ({ ...tab, number: String(index + 1).padStart(2, '0') }))}
      />
      <PrototypePageHeader
        title={`产业链拆解 - ${activeModuleTab.label}`}
        subtitle="政策证据 · 三模式解构 · 公司映射 · 研究闭环"
        dataFreshness={(
          <DataFreshnessBar
            tradeDate={dataFreshness.market?.latest_trade_date}
            updatedAt={dataFreshness.research_reports?.latest_pub_date || dataFreshness.market?.latest_trade_date}
            source="screener/supply-chain/workbench"
          />
        )}
        actions={[
          { key: 'public', label: '公共产业图谱', active: true, tone: 'neutral' },
          { key: 'private', label: '账户私有观察池', tone: 'up' },
          { key: 'research', label: researchCollectionLabel(researchIngestion.auto_collection_status), tone: 'warn' },
        ]}
      />
      <div className="kpis">
        <MetricCard label="当前主题" value={selectedTheme?.name || selectedNode?.policy_theme || '政策主题'} sub={model.name || '产业链解构选股模型 V4'} tone="accent" />
        <MetricCard label="候选公司" value={activeCandidates.length} sub={upstreamCandidates.length ? `上游观察 ${upstreamCandidates.length}` : '全局观察池'} tone="up" />
        <MetricCard label="BOM 节点" value={nodes.length} sub={`当前模式：${methodSummary.title}`} tone="muted" />
        <MetricCard label="数据更新" value={dataFreshness.market?.latest_trade_date || '--'} sub={dataFreshness.research_reports?.latest_pub_date ? `研报 ${dataFreshness.research_reports.latest_pub_date}` : '等待数据同步'} tone="warn" />
      </div>

      {mappingQualityError && (
        <Alert
          type="warning"
          showIcon
          message="映射质量接口不可用"
          description={mappingQualityError}
          style={{ marginBottom: 16 }}
        />
      )}

      {chainDeconstructError && (
        <Alert
          type="error"
          showIcon
          message="产业链拆解接口不可用"
          description={chainDeconstructError}
          style={{ marginBottom: 16 }}
        />
      )}

      <SupplyChainResearchWorkbench
        themes={themes}
        nodes={nodes}
        candidates={activeCandidates}
        selectedThemeId={selectedThemeId}
        selectedNodeId={selectedNodeId}
        selectedNodeThesis={selectedNodeThesis}
        mappingQuality={mappingQuality}
        loading={loading || candidateLoading}
        onSelectTheme={selectTheme}
        onSelectNode={selectNodeById}
        onOpenCompany={openCompany}
        onReviewMapping={reviewMapping}
      />

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={7}>
          <div style={{ border: '1px solid #f0f0f0', borderRadius: 8, background: '#fff', padding: 12, minHeight: 360 }}>
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <Title level={5} style={{ margin: 0 }}>BOM层层拆解</Title>
              {/* P2-09: Use ChainTreeChart instead of Antd Tree */}
              <ChainTreeChart
                themes={themes}
                nodes={nodes}
                selectedThemeId={selectedThemeId}
                selectedNodeId={selectedNodeId}
                onNodeClick={selectNode}
                onThemeClick={theme => selectTheme(theme.theme_id)}
                height={280}
              />
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
            {/* P2-08: MethodSelector for three view tabs */}
            <div style={{ padding: '8px 12px', borderBottom: '1px solid #f0f0f0' }}>
              <MethodSelector
                value={chainMethod}
                onChange={setChainMethod}
                loading={chainLoading}
                disabled={!selectedThemeId}
              />
            </div>
            <ReactECharts
              option={graphOption}
              style={{ height: 214 }}
              onEvents={{
                click: (params: any) => {
                  const nextNode = nodes.find(node => node.node_id === params?.data?.id)
                  if (nextNode) selectNode(nextNode)
                },
              }}
            />
            <div style={{ borderTop: '1px solid #f0f0f0', padding: '10px 12px' }}>
              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                <Space align="baseline" style={{ justifyContent: 'space-between', width: '100%' }}>
                  <Text strong>{methodSummary.title}</Text>
                  <Tag color={chainMethod === 'value_chain' ? 'gold' : chainMethod === 'competition' ? 'purple' : 'blue'}>
                    {chainLoading ? '加载中' : '已切换'}
                  </Tag>
                </Space>
                <Text type="secondary" style={{ fontSize: 12 }}>{methodSummary.desc}</Text>
                <Row gutter={8}>
                  {methodSummary.stats.map(([label, value]) => (
                    <Col span={8} key={label}>
                      <div style={{ background: '#f7f9fc', border: '1px solid #eef2f8', borderRadius: 6, padding: 8 }}>
                        <div style={{ fontSize: 11, color: '#8a96a8' }}>{label}</div>
                        <div style={{ fontSize: 12, fontWeight: 700, color: '#1a2230' }}>{value}</div>
                      </div>
                    </Col>
                  ))}
                </Row>
              </Space>
            </div>
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
            <Space wrap>
              <Title level={5} style={{ margin: 0 }}>候选公司池</Title>
              <Tag color="blue">{displayCandidates.length} 候选</Tag>
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
                  candidates={displayCandidates}
                  loading={candidateLoading || chainCandidateLoading}
                  onPointClick={openCompany}
                  themeName={selectedTheme?.name || selectedNode?.policy_theme}
                  style={{ height: 420 }}
                />
              </Col>
              <Col xs={24} lg={12}>
                <CandidateCompanyTable
                  candidates={displayCandidates}
                  loading={candidateLoading || chainCandidateLoading}
                  selectedNodeName={selectedNode?.name}
                  mappingMessage={selectedNodeThesis.mapping_message}
                  onOpenCompany={openCompany}
                />
              </Col>
            </Row>
          )}

          {/* Show table only when bubble chart is hidden */}
          {!showBubbleChart && (
            <CandidateCompanyTable
              candidates={displayCandidates}
              loading={candidateLoading || chainCandidateLoading}
              selectedNodeName={selectedNode?.name}
              mappingMessage={selectedNodeThesis.mapping_message}
              onOpenCompany={openCompany}
            />
          )}
        </Space>
      </div>

      <div style={{ marginTop: 16 }}>
        <SupplyChainMappingReviewPanel />
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

      {/* P2-08: Policy interpretation section (replaces LLM extraction) */}
      <div style={{ marginTop: 16, border: '1px solid #f0f0f0', borderRadius: 8, background: '#fff', padding: 16 }}>
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Space wrap>
            <Text strong><FileTextOutlined style={{ marginRight: 6 }} />政策解读</Text>
            <Tag color={researchCollectionColor(researchIngestion.auto_collection_status)}>
              {researchCollectionLabel(researchIngestion.auto_collection_status)}
            </Tag>
            {policyResult?.status && (
              <Tag color={policyResult.status === 'ok' ? 'green' : policyResult.status === 'disabled' ? 'gold' : 'red'}>
                {policyResult.status === 'ok' ? '解读成功' : policyResult.status === 'disabled' ? '功能未启用' : '解读失败'}
              </Tag>
            )}
            {policyResult?.usage && (
              <Tag color="purple">
                tokens: {policyResult.usage.total_tokens}
              </Tag>
            )}
          </Space>
          {researchIngestion.message && (
            <Text type="secondary">{researchIngestion.message}</Text>
          )}
          <TextArea
            value={policyText}
            onChange={e => setPolicyText(e.target.value)}
            placeholder="粘贴政策文件、公告、新闻稿文本，LLM将自动解读并提取产业主题与投资逻辑..."
            autoSize={{ minRows: 4, maxRows: 8 }}
          />
          <Space wrap>
            <Button
              type="primary"
              icon={<ScanOutlined />}
              loading={policyLoading}
              disabled={!policyText.trim()}
              onClick={runPolicyInterpret}
            >
              解读政策
            </Button>
            <Checkbox checked={persistPolicy} onChange={e => setPersistPolicy(e.target.checked)}>
              写入待审核图谱
            </Checkbox>
            {policyResult?.persisted && <Tag color="green">已写入</Tag>}
          </Space>
          {policyResult?.interpretation_result && (
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              {policyResult.interpretation_result.summary && (
                <Paragraph style={{ marginBottom: 0, background: '#f5f5f5', padding: 8, borderRadius: 4 }}>
                  {policyResult.interpretation_result.summary}
                </Paragraph>
              )}
              {policyResult.interpretation_result.investment_logic && (
                <Text type="secondary">投资逻辑: {policyResult.interpretation_result.investment_logic}</Text>
              )}
              {!!policyResult.interpretation_result.industry_themes?.length && (
                <Space wrap>
                  <Text>产业主题:</Text>
                  {policyResult.interpretation_result.industry_themes.map((t: any, idx: number) => (
                    <Tag key={idx} color="blue">{t.name || t}</Tag>
                  ))}
                </Space>
              )}
              {!!policyResult.interpretation_result.bom_nodes?.length && (
                <Space wrap>
                  <Text>BOM节点:</Text>
                  {policyResult.interpretation_result.bom_nodes.map((node: string, idx: number) => (
                    <Tag key={idx}>{node}</Tag>
                  ))}
                </Space>
              )}
              {!!policyResult.interpretation_result.risk_factors?.length && (
                <Space wrap>
                  <Text>风险因素:</Text>
                  {policyResult.interpretation_result.risk_factors.map((r: any, idx: number) => (
                    <Tag key={idx} color="orange">{r.name || r}</Tag>
                  ))}
                </Space>
              )}
            </Space>
          )}
        </Space>
      </div>

      <CompanyResearchDrawer
        open={companyOpen}
        company={companyDetail}
        onClose={() => setCompanyOpen(false)}
      />
    </PrototypePage>
  )
}
