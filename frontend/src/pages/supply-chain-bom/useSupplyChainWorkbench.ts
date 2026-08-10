// SupplyChainBom 数据编排 hook：workbench 加载、链路拆解、映射复核、节点选择
// 从 SupplyChainBom.tsx 拆出，主文件只保留页面装配与 UI 状态

import { useEffect, useMemo, useState } from 'react'
import { message } from 'antd'
import {
  screenerApi,
  chainApi,
  type ChainDeconstructResponse,
  type SupplyChainMappingQuality,
  type SupplyChainMappingReviewDecision,
} from '../../api/client'
import type { SupplyChainNode, SupplyChainTheme } from '../../api/types'
import type { ChainMethod, ChainOverlay } from './MethodSelector'
import type {
  BomNode,
  CandidateCompany,
  ChainTemplateKey,
  ResearchIngestionStatus,
  SelectedNodeThesis,
  SupplyChainDataFreshness,
  ThemeRow,
  WorkbenchModel,
} from './types'
import {
  chainDeconstructErrorText,
  chainMethodSummary,
  flattenChainNodes,
  mappingQualityErrorText,
} from './helpers'

export function useSupplyChainWorkbench() {
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
  const [loading, setLoading] = useState(false)
  const [candidateLoading, setCandidateLoading] = useState(false)
  const [mappingQuality, setMappingQuality] = useState<SupplyChainMappingQuality | null>(null)
  const [workbenchError, setWorkbenchError] = useState('')
  const [catalogSource, setCatalogSource] = useState('screener/supply-chain/workbench')

  // 拆解架构整合 Step4: 主视图固定 upstream_downstream 单树, value_chain/competition
  // 降级为可叠加 overlay 开关 (ChainMethod 类型保留, bom 钻取链仍在用)
  const chainMethod: ChainMethod = 'upstream_downstream'
  const [chainOverlays, setChainOverlays] = useState<ChainOverlay[]>([])
  const [chainTemplate, setChainTemplate] = useState<ChainTemplateKey>('default')
  const [chainDeconstructResult, setChainDeconstructResult] = useState<ChainDeconstructResponse | null>(null)
  const [chainLoading, setChainLoading] = useState(false)
  const [chainDeconstructError, setChainDeconstructError] = useState('')
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // P2-08/Step4: Fetch chain deconstruct when overlays/template change and theme is selected
  useEffect(() => {
    if (!selectedThemeId) return
    let mounted = true
    setChainLoading(true)
    setChainDeconstructError('')
    const template = chainTemplate === 'default' ? undefined : chainTemplate
    chainApi.deconstructChain({
      theme_id: selectedThemeId,
      method: chainMethod,
      template,
      overlays: chainOverlays.length > 0 ? chainOverlays : undefined,
    })
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedThemeId, chainOverlays, chainTemplate])

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

  const addThemes = (newThemes: ThemeRow[]) => {
    setThemes(prev => [...prev, ...newThemes])
  }

  return {
    themes,
    nodes,
    edges,
    model,
    candidates,
    nodeCandidates,
    upstreamCandidates,
    selectedNodeThesis,
    dataFreshness,
    researchIngestion,
    selectedThemeId,
    selectedNodeId,
    nodeDetail,
    loading,
    candidateLoading,
    mappingQuality,
    mappingQualityError,
    workbenchError,
    catalogSource,
    chainOverlays,
    chainTemplate,
    chainDeconstructResult,
    chainLoading,
    chainDeconstructError,
    selectedTheme,
    selectedNode,
    filteredNodes,
    activeCandidates,
    methodSummary,
    setChainOverlays,
    setChainTemplate,
    selectTheme,
    selectNode,
    selectNodeById,
    reviewMapping,
    addThemes,
  }
}
