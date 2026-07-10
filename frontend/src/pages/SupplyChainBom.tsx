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
import SupplyChainCandidateRankingPanel from './supply-chain-bom/SupplyChainCandidateRankingPanel'
import SupplyChainCapexEvidenceReviewPanel from './supply-chain-bom/SupplyChainCapexEvidenceReviewPanel'
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
import { lightTokens, alpha, signalLevelTokens } from '../styles/tokens'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

/** 卡脖子等级 → 颜色（红涨绿跌：一级=红/二级=黄/非=绿，对齐 preview 4.2 ckColor） */
function ckColor(level?: string) {
  if (level === 'primary') return lightTokens.up
  if (level === 'secondary') return lightTokens.warn
  return lightTokens.down
}

/** accent 半透明叠色（echarts bar/scatter 用，token 派生自 lightTokens.accent #3d8bff） */
const ACCENT_OVERLAY = alpha.accent(0.45)
const ACCENT_OVERLAY_SOFT = alpha.accent(0.28)

// ===== 4.1 policy-analysis helpers =====
const POLICY_STRENGTH_LABELS = [
  '1/5 — 轻微提及',
  '2/5 — 一般关注',
  '3/5 — 中等力度',
  '4/5 — 强力政策',
  '5/5 — 最高级别',
]

// 政策强度从 risk_factors / interpretation 字段启发式推断（无独立 strength 字段时）
function inferPolicyStrength(result: PolicyInterpretResponse['interpretation_result'] | undefined): number {
  if (!result) return 0
  const text = `${result.summary || ''} ${result.investment_logic || ''}`
  let score = 2
  if (/大基金|3000亿|千亿|国家重大|重大科技专项|三年行动|五年规划/.test(text)) score = 4
  if (/最高级别|战略|举国|核心攻关/.test(text)) score = 5
  if (result.industry_themes?.length >= 3) score = Math.max(score, 3)
  return Math.min(5, Math.max(1, score))
}

// 方向卡片：从 industry_themes 派生（preview direction cards）
type PolicyDirection = { name: string; desc: string }
function derivePolicyDirections(result: PolicyInterpretResponse['interpretation_result'] | undefined): PolicyDirection[] {
  if (!result?.industry_themes?.length) return []
  return result.industry_themes.map((t: Record<string, unknown>) => ({
    name: String(t.name || t.theme || '未命名方向'),
    desc: String(t.logic || t.rationale || t.summary || result.investment_logic || ''),
  }))
}

// 行业映射行：从 bom_nodes 派生（preview mapping-table）
type PolicyMapping = { direction: string; industry: string; concept: string; conf: 'exact' | 'llm' | 'low' }
function derivePolicyMappings(directions: PolicyDirection[], bomNodes: string[]): PolicyMapping[] {
  const rows: PolicyMapping[] = []
  directions.forEach((d, idx) => {
    const bomNode = bomNodes[idx] || bomNodes[0] || ''
    rows.push({
      direction: d.name,
      industry: bomNode || d.name,
      concept: `ths_${(bomNode || d.name).slice(0, 6)}`,
      conf: idx < bomNodes.length ? 'exact' : 'llm',
    })
  })
  return rows
}

function confBadgeClass(conf: 'exact' | 'llm' | 'low') {
  if (conf === 'exact') return 'conf-exact'
  if (conf === 'llm') return 'conf-llm'
  return 'conf-low'
}
function confBadgeLabel(conf: 'exact' | 'llm' | 'low') {
  if (conf === 'exact') return '精确匹配'
  if (conf === 'llm') return 'LLM推断'
  return '低置信'
}

// ===== 4.3 company-analysis helpers =====
// 护城河评分维度（preview moat-table 5 列权重）
const MOAT_DIMENSIONS: { key: string; label: string; weight: number; tone: 'high' | 'mid' | 'low' }[] = [
  { key: 'moat', label: '护城河', weight: 0.30, tone: 'high' },
  { key: 'growth', label: '增长力', weight: 0.20, tone: 'high' },
  { key: 'profit', label: '利润率', weight: 0.15, tone: 'mid' },
  { key: 'irreplaceable', label: '不可替代', weight: 0.25, tone: 'high' },
  { key: 'domestic', label: '国产替代', weight: 0.10, tone: 'mid' },
]

// 从 dimension_scores 派生 5 维护城河分数（兼容多种 key 命名）
function moatScore(c: CandidateCompany, dim: typeof MOAT_DIMENSIONS[number]): number | null {
  const ds = c.dimension_scores || {}
  const candidates: Record<string, number | undefined> = {
    moat: ds.moat ?? ds.moat_score ?? ds.护城河,
    growth: ds.growth ?? ds.growth_score ?? ds.增长力,
    profit: ds.profit ?? ds.profitability ?? ds.margin ?? ds.gross_margin ?? c.gross_margin,
    irreplaceable: ds.irreplaceable ?? ds.irreplaceability ?? ds.criticality ?? c.chokepoint_score,
    domestic: ds.domestic ?? ds.domestic_substitution ?? ds.policy_match ?? c.policy_match_score,
  }
  const v = candidates[dim.key]
  if (v === undefined || v === null || !Number.isFinite(Number(v))) return null
  return Number(v)
}

function scoreToStars(score: number | null): { filled: number; off: number } {
  if (score === null) return { filled: 0, off: 5 }
  const filled = Math.max(0, Math.min(5, Math.round(score / 20)))
  return { filled, off: 5 - filled }
}

function scoreClass(score: number | null): 'high' | 'mid' | 'low' {
  if (score === null) return 'low'
  if (score >= 85) return 'high'
  if (score >= 70) return 'mid'
  return 'low'
}

// 综合分（preview composite = 各维加权）
function compositeScore(c: CandidateCompany): number | null {
  let total = 0
  let weightCovered = 0
  MOAT_DIMENSIONS.forEach(dim => {
    const s = moatScore(c, dim)
    if (s !== null) {
      total += s * dim.weight
      weightCovered += dim.weight
    }
  })
  if (weightCovered === 0) return c.score ?? null
  return Math.round(total / weightCovered)
}

// 卡脖子分级（preview bottleneck grid 3 列）
type BottleneckTier = 'l1' | 'l2' | 'l0'
function bottleneckTier(c: CandidateCompany): BottleneckTier {
  const ck = c.chokepoint_score
  if (ck !== undefined && Number.isFinite(Number(ck))) {
    const v = Number(ck)
    if (v >= 70) return 'l1'
    if (v >= 40) return 'l2'
    return 'l0'
  }
  // fallback：从 dimension_scores.irreplaceable 或 impact_role 推断
  const ir = c.dimension_scores?.irreplaceable ?? c.dimension_scores?.criticality
  if (ir !== undefined && Number.isFinite(Number(ir))) {
    const v = Number(ir)
    if (v >= 70) return 'l1'
    if (v >= 40) return 'l2'
    return 'l0'
  }
  const role = c.impact_role || ''
  if (role.includes('核心') || role.includes('critical')) return 'l1'
  if (role.includes('重要') || role.includes('strategic')) return 'l2'
  return 'l0'
}

const BOTTLENECK_META: Record<BottleneckTier, { label: string; icon: string; cls: string }> = {
  l1: { label: '一级卡脖子', icon: '🔴', cls: 'bn-l1' },
  l2: { label: '二级卡脖子', icon: '🟡', cls: 'bn-l2' },
  l0: { label: '非卡脖子', icon: '🟢', cls: 'bn-l0' },
}

// 三重共振（preview comm-table 共振分）
function resonanceScore(c: CandidateCompany): number {
  const cycle = c.commercialization_cycle || c.commercialization_stage || ''
  const policy = c.policy_match_score ?? c.dimension_scores?.policy_match
  const yieldNum = c.performance_yield ?? c.dimension_scores?.performance
  let s = 0
  if (/成长|growth/i.test(cycle)) s += 0.35
  else if (/导入|intro/i.test(cycle)) s += 0.15
  else if (/成熟|mature/i.test(cycle)) s += 0.20
  if (policy !== undefined && Number.isFinite(Number(policy))) s += (Number(policy) / 100) * 0.35
  if (yieldNum !== undefined && Number.isFinite(Number(yieldNum))) s += Math.min(0.30, Number(yieldNum) / 100 * 0.30)
  return Math.min(1, Math.round(s * 100) / 100)
}

function resonanceTone(score: number): 'triple' | 'waiting' | 'none' {
  if (score >= 0.40) return 'triple'
  if (score >= 0.15) return 'waiting'
  return 'none'
}

function commPhaseClass(cycle: string | undefined): string {
  if (!cycle) return 'comm-intro'
  if (/成长|growth/i.test(cycle)) return 'comm-growth'
  if (/成熟|mature/i.test(cycle)) return 'comm-mature'
  return 'comm-intro'
}
function commPhaseLabel(cycle: string | undefined): string {
  if (!cycle) return '导入期'
  if (/成长|growth/i.test(cycle)) return '成长期'
  if (/成熟|mature/i.test(cycle)) return '成熟期'
  if (/导入|intro/i.test(cycle)) return '导入期'
  return cycle
}

const supplyChainTabs = [
  { key: 'policy', path: '/supply-chain-bom/policy', label: '政策梳理', subLabel: '政策证据' },
  { key: 'chain', path: '/supply-chain-bom', label: '产业链解构', subLabel: '三种模式' },
  { key: 'company', path: '/supply-chain-bom/company', label: '多维度分析', subLabel: '公司对比' },
  { key: 'ranking', path: '/supply-chain-bom/ranking', label: '候选总榜', subLabel: '真实排序' },
  { key: 'capex-review', path: '/supply-chain-bom/capex-review', label: 'CAPEX审核', subLabel: '证据入库' },
]

function activeSupplyChainTab(pathname: string) {
  if (pathname.startsWith('/supply-chain-bom/policy')) return 'policy'
  if (pathname.startsWith('/supply-chain-bom/company')) return 'company'
  if (pathname.startsWith('/supply-chain-bom/ranking')) return 'ranking'
  if (pathname.startsWith('/supply-chain-bom/capex-review')) return 'capex-review'
  return 'chain'
}

interface WorkbenchModel {
  name?: string
  philosophy?: string
  score_dimensions?: ScoreDimension[]
}

interface ChainMethodSummary {
  title: string
  desc: string
  stats: Array<[string, string]>
}

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

function chainMethodSummary(method: ChainMethod): ChainMethodSummary {
  if (method === 'value_chain') {
    return {
      title: '价值链拆解',
      desc: '按原材料、核心零部件、制造设备、封装测试拆分利润池，突出毛利率、议价权和国产替代空间。',
      stats: [],
    }
  }
  if (method === 'competition') {
    return {
      title: '竞争格局',
      desc: '按市场份额、技术壁垒、市值体量和客户绑定关系评估公司位置，区分龙头、跟随者和卡位标的。',
      stats: [],
    }
  }
  return {
    title: '上下游拆解',
    desc: '从政策主题向上游材料、核心部件、制造设备、下游应用逐层展开，定位可跟踪节点和映射公司。',
    stats: [],
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
  const [workbenchError, setWorkbenchError] = useState('')
  const [catalogSource, setCatalogSource] = useState('screener/supply-chain/workbench')

  // P2-08: Policy interpretation state (replaces LLM extraction)
  const [policyText, setPolicyText] = useState('')
  const [policyResult, setPolicyResult] = useState<PolicyInterpretResponse | null>(null)
  const [policyLoading, setPolicyLoading] = useState(false)
  const [persistPolicy, setPersistPolicy] = useState(false)

  // P2-08: Chain method selector state
  const [chainMethod, setChainMethod] = useState<ChainMethod>('upstream_downstream')
  const [chainTemplate, setChainTemplate] = useState<ChainTemplateKey>('default')
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
    const nextThemes = (data.themes || data.policy_themes || []).map((theme: any) => ({
      ...theme,
      theme_id: theme.theme_id || theme.id,
    }))
    const nextNodes = (data.nodes || data.graph_nodes || []).map((node: any) => ({
      ...node,
      theme_id: node.theme_id || node.themeId || data.selected_theme_id || node.chain_id,
    }))
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

    const selectInitialCatalog = (data: any) => {
      const nextThemes = (data.themes || data.policy_themes || []) as (SupplyChainTheme & { theme_id?: string })[]
      const firstTheme = nextThemes[0]
      setSelectedThemeId((data as { selected_theme_id?: string }).selected_theme_id || firstTheme?.theme_id || firstTheme?.id || '')
      setSelectedNodeId((data as { selected_node_id?: string }).selected_node_id || '')
    }

    const loadInitialWorkbench = async () => {
      setLoading(true)
      setWorkbenchError('')
      setCatalogSource('screener/supply-chain/workbench')
      try {
        const resp = await screenerApi.getSupplyChainWorkbench({ topN: 30 })
        if (!mounted) return
        const data = resp.data || {}
        applyWorkbenchPayload(data, true)
        selectInitialCatalog(data)
      } catch (err) {
        if (!mounted) return
        setWorkbenchError('workbench 返回异常，已改用真实 screener/supply-chain/bom 图谱数据；候选池和数据新鲜度需要 workbench 恢复后刷新。')
        setCatalogSource('screener/supply-chain/bom')
        try {
          const resp = await screenerApi.getSupplyChainBom()
          if (!mounted) return
          const data = {
            ...(resp.data || {}),
            candidates: [],
            node_candidate_companies: [],
            upstream_influence_candidates: [],
            selected_node_thesis: {},
          }
          applyWorkbenchPayload(data, true)
          selectInitialCatalog(data)
        } catch (fallbackErr) {
          if (!mounted) return
          message.error('产业链真实图谱加载失败，请检查 screener-service')
        }
      } finally {
        if (mounted) setLoading(false)
      }
    }

    loadInitialWorkbench()
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
    const template = chainTemplate === 'default' ? undefined : chainTemplate
    chainApi.deconstructChain({ theme_id: selectedThemeId, method: chainMethod, template })
      .then(resp => {
        if (!mounted) return
        const data = resp.data as ChainDeconstructResponse
        setChainDeconstructResult(data)
        setChainDeconstructError('')
        // 模板视图只展示链路逻辑，不覆盖原有 BOM 节点和股票映射。
        if (!template && data.tree) {
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
  }, [selectedThemeId, chainMethod, chainTemplate])

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
    const nodePalette = [lightTokens.accent, lightTokens.down, lightTokens.muted]
    const graphNodes = filteredNodes.map((node, index) => ({
      id: node.node_id,
      name: node.name,
      value: node.policy_theme,
      symbolSize: selectedNodeId === node.node_id ? 62 : 48,
      x: Math.cos((index / Math.max(1, filteredNodes.length)) * Math.PI * 2) * 180,
      y: Math.sin((index / Math.max(1, filteredNodes.length)) * Math.PI * 2) * 120,
      itemStyle: {
        color: selectedNodeId === node.node_id ? lightTokens.up : nodePalette[index % 3],
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
        lineStyle: { color: lightTokens.muted, width: 1.2 },
        label: { color: lightTokens.fg, fontSize: 12 },
      }],
    }
  }, [edges, filteredNodes, selectedNodeId])

  /** 4.2：从 chainDeconstructResult.tree（SupplyChainNode）收集叶子节点，供 value/competition 图 */
  const chainLeaves = useMemo<SupplyChainNode[]>(() => {
    const tree = chainDeconstructResult?.tree as SupplyChainNode | undefined
    if (!tree) return []
    const out: SupplyChainNode[] = []
    const walk = (node: SupplyChainNode) => {
      if (node.children && node.children.length > 0) {
        node.children.forEach(walk)
      } else {
        out.push(node)
      }
    }
    walk(tree)
    return out
  }, [chainDeconstructResult])

  /** 4.2 value_chain 模式：毛利率/价值增值横向对比 bar（对齐 preview valueChart） */
  const valueChainOption = useMemo(() => {
    const rows = chainLeaves.length > 0 ? chainLeaves : []
    return {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: 88, right: 70, top: 24, bottom: 32 },
      xAxis: {
        type: 'value',
        name: '毛利率(%)',
        max: 60,
        axisLabel: { color: lightTokens.muted },
        axisLine: { lineStyle: { color: lightTokens.border } },
        splitLine: { lineStyle: { color: lightTokens.border, type: 'dashed' } },
      },
      yAxis: {
        type: 'category',
        inverse: true,
        data: rows.map(node => node.name),
        axisLabel: { color: lightTokens.fg2, fontWeight: 650 },
        axisLine: { lineStyle: { color: lightTokens.border } },
      },
      series: [
        {
          name: '毛利率',
          type: 'bar',
          barWidth: 22,
          data: rows.map(node => node.value_chain?.margin ?? 0),
          itemStyle: { color: lightTokens.accent, borderRadius: [0, 5, 5, 0] },
          label: { show: true, position: 'right', formatter: '{c}%', color: lightTokens.fg2, fontWeight: 700 },
        },
        {
          name: '价值增值',
          type: 'bar',
          barWidth: 10,
          barGap: '-72%',
          data: rows.map(node => node.value_chain?.value_added ?? 0),
          itemStyle: { color: ACCENT_OVERLAY, borderRadius: [0, 4, 4, 0] },
        },
      ],
    }
  }, [chainLeaves])

  /** 4.2 competition 模式：市场份额 × 议价权 × 候选数气泡图（对齐 preview competitionChart） */
  const competitionOption = useMemo(() => {
    const rows = chainLeaves
    return {
      tooltip: {
        formatter: (p: any) => {
          const n = rows[p.dataIndex]
          if (!n) return ''
          return `${n.name}<br/>议价权: ${n.value_chain?.pricing_power ?? '--'}<br/>价值增值: ${n.value_chain?.value_added ?? '--'}`
        },
      },
      grid: { left: 60, right: 36, top: 36, bottom: 50 },
      xAxis: {
        name: '议价权',
        max: 100,
        axisLabel: { color: lightTokens.muted },
        nameTextStyle: { color: lightTokens.muted },
        splitLine: { lineStyle: { color: lightTokens.border, type: 'dashed' } },
      },
      yAxis: {
        name: '价值增值(%)',
        max: 100,
        axisLabel: { color: lightTokens.muted },
        nameTextStyle: { color: lightTokens.muted },
        splitLine: { lineStyle: { color: lightTokens.border, type: 'dashed' } },
      },
      series: [{
        type: 'scatter',
        data: rows.map(node => {
          const cap = Math.max(8, (node.value_chain?.value_added ?? 10) * 1.2)
          return {
            name: node.name,
            value: [node.value_chain?.pricing_power ?? 0, node.value_chain?.value_added ?? 0, cap],
            symbolSize: Math.max(28, Math.min(80, cap)),
            itemStyle: { color: ACCENT_OVERLAY_SOFT, borderColor: lightTokens.accent, borderWidth: 2 },
            label: { show: true, formatter: '{b}', color: lightTokens.fg2, fontSize: 10, fontWeight: 700 },
          }
        }),
        emphasis: { scale: 1.16 },
      }],
    }
  }, [chainLeaves])

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
            source={catalogSource}
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

      {workbenchError && (
        <Alert
          type="warning"
          showIcon
          message="组合工作台接口不可用"
          description={workbenchError}
          style={{ marginBottom: 16 }}
        />
      )}

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

      {activeModuleKey === 'capex-review' ? (
        <SupplyChainCapexEvidenceReviewPanel />
      ) : activeModuleKey === 'ranking' ? (
        <SupplyChainCandidateRankingPanel onOpenCompany={openCompany} />
      ) : (
        <>
          <SupplyChainResearchWorkbench
            themes={themes}
            nodes={nodes}
            candidates={activeCandidates}
            selectedThemeId={selectedThemeId}
            selectedNodeId={selectedNodeId}
            selectedNodeThesis={selectedNodeThesis}
            mappingQuality={mappingQuality}
            chainTemplate={chainTemplate}
            templateResult={chainDeconstructResult}
            loading={loading || candidateLoading}
            onChainTemplateChange={setChainTemplate}
            onSelectTheme={selectTheme}
            onSelectNode={selectNodeById}
            onOpenCompany={openCompany}
            onReviewMapping={reviewMapping}
          />

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={7}>
          <div style={{ border: `1px solid ${lightTokens.border}`, borderRadius: lightTokens.radius, background: lightTokens.surface, padding: 12, minHeight: 360 }}>
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
          <div style={{ minHeight: 360, border: `1px solid ${lightTokens.border}`, borderRadius: lightTokens.radius, background: lightTokens.surface }}>
            {/* P2-08: MethodSelector for three view tabs */}
            <div style={{ padding: '8px 12px', borderBottom: `1px solid ${lightTokens.border}` }}>
              <MethodSelector
                value={chainMethod}
                onChange={setChainMethod}
                loading={chainLoading}
                disabled={!selectedThemeId}
              />
            </div>
            {/* 4.2 AC①：三模式专属渲染（非通用壳） */}
            {chainMethod === 'upstream_downstream' && (
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
            )}
            {chainMethod === 'value_chain' && (
              <ReactECharts option={valueChainOption} style={{ height: 214 }} />
            )}
            {chainMethod === 'competition' && (
              <ReactECharts option={competitionOption} style={{ height: 214 }} />
            )}
            {filteredNodes.length === 0 && (
              <div style={{ padding: 24, textAlign: 'center', color: lightTokens.muted, fontSize: 12 }}>
                暂无该主题的拆解节点，切换主题或等待 chain-service 返回。
              </div>
            )}
            <div style={{ borderTop: `1px solid ${lightTokens.border}`, padding: '10px 12px' }}>
              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                <Space align="baseline" style={{ justifyContent: 'space-between', width: '100%' }}>
                  <Text strong>{methodSummary.title}</Text>
                  <Tag color={chainMethod === 'value_chain' ? 'gold' : chainMethod === 'competition' ? 'purple' : 'blue'}>
                    {chainLoading ? '加载中' : '已切换'}
                  </Tag>
                </Space>
                <Text type="secondary" style={{ fontSize: 12 }}>{methodSummary.desc}</Text>
                {/* 4.2 mode-note：value/competition 三卡注释（对齐 preview mode-note） */}
                {chainMethod !== 'upstream_downstream' && (
                  <Row gutter={8}>
                    {(chainMethod === 'value_chain'
                      ? [['最高毛利环节', '核心零部件', '技术壁垒最高，国产替代难度最大。'], ['利润兑现', '设备制造', '订单和业绩兑现最直接，是从政策受益走向利润兑现的核心环节。'], ['低毛利环节', '封装测试', '毛利率最低，受先进封装投资周期带动。']]
                      : [['寡头垄断', '光刻系统', '全球极高集中度，A股通过光刻胶/光学元件/配套设备参与。'], ['国产突破', '刻蚀/PVD', '进入高壁垒高成长象限，订单兑现与扩产节奏最关键。'], ['分散竞争', '清洗/检测', '国产化率较高，按订单和利润率筛选。']]
                    ).map(([label, value, sub]) => (
                      <Col span={8} key={label as string}>
                        <div style={{ background: lightTokens.surface2, border: `1px solid ${lightTokens.border}`, borderRadius: 7, padding: '8px 10px' }}>
                          <div style={{ fontSize: 10, color: lightTokens.muted, marginBottom: 4 }}>{label}</div>
                          <div style={{ fontSize: 13, fontWeight: 700, color: lightTokens.fg }}>{value}</div>
                          <div style={{ fontSize: 10, color: lightTokens.fg2, marginTop: 2, lineHeight: 1.5 }}>{sub}</div>
                        </div>
                      </Col>
                    ))}
                  </Row>
                )}
                <Row gutter={8}>
                  {methodSummary.stats.map(([label, value]) => (
                    <Col span={8} key={label}>
                      <div style={{ background: lightTokens.surface2, border: `1px solid ${lightTokens.elevated}`, borderRadius: 6, padding: 8 }}>
                        <div style={{ fontSize: 11, color: lightTokens.muted }}>{label}</div>
                        <div style={{ fontSize: 12, fontWeight: 700, color: lightTokens.fg }}>{value}</div>
                      </div>
                    </Col>
                  ))}
                  {methodSummary.stats.length === 0 && chainMethod === 'upstream_downstream' && (
                    <Col span={24}>
                      <Text type="secondary" style={{ fontSize: 12 }}>上下游图展示节点拓扑，点击节点下钻候选公司。</Text>
                    </Col>
                  )}
                </Row>
              </Space>
            </div>
          </div>
        </Col>

        <Col xs={24} lg={7}>
          <div style={{ border: `1px solid ${lightTokens.border}`, borderRadius: lightTokens.radius, background: lightTokens.surface, padding: 16, minHeight: 360 }}>
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
          <div style={{ minHeight: 276, border: `1px solid ${lightTokens.border}`, borderRadius: lightTokens.radius, background: lightTokens.surface, padding: 16 }}>
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
          <div style={{ marginTop: 16, border: `1px solid ${lightTokens.border}`, borderRadius: lightTokens.radius, background: lightTokens.surface, padding: 16 }}>
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
                <Paragraph style={{ marginBottom: 0, background: lightTokens.surface2, padding: 8, borderRadius: 4 }}>
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
        </>
      )}

      <CompanyResearchDrawer
        open={companyOpen}
        company={companyDetail}
        onClose={() => setCompanyOpen(false)}
      />
    </PrototypePage>
  )
}
