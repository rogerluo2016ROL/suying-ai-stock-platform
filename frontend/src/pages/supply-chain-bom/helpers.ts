// 供应链 BOM 页共享 helpers：纯函数、接口错误文案、页签配置
// 从 SupplyChainBom.tsx 拆出（UI 状态下沉，共享数据走 props）

import type { ChainNode } from '../../api/client'
import type { ChainMethod } from './MethodSelector'
import type { BomNode } from './types'

export function formatChangePct(value?: number) {
  const n = Number(value)
  if (!Number.isFinite(n)) return '--'
  return `${n > 0 ? '+' : ''}${n.toFixed(2)}%`
}

export function researchCollectionLabel(status?: string) {
  if (status === 'enabled') return '研报自动采集已启用'
  if (status === 'llm_key_missing') return '等待研报智能解读授权'
  if (status === 'local_catalog_available') return '研报库已接入'
  return '研报源未配置'
}

export function researchCollectionColor(status?: string) {
  if (status === 'enabled') return 'green'
  if (status === 'local_catalog_available') return 'blue'
  if (status === 'llm_key_missing') return 'gold'
  return 'orange'
}

export function endpointStatus(error: unknown) {
  return (error as { response?: { status?: number } })?.response?.status
}

export function mappingQualityErrorText(error: unknown) {
  const status = endpointStatus(error)
  if (status === 404) {
    return '当前服务未暴露 /api/v1/screener/supply-chain/mapping-review/quality，请重建或更新 screener-service；图谱和候选池仍可继续查看。'
  }
  return '映射质量报告加载失败，请检查 screener-service 和网关状态。'
}

export function chainDeconstructErrorText(error: unknown) {
  const status = endpointStatus(error)
  if (status === 500) return '拆解接口返回 500，当前图谱可能是旧数据或默认目录。请检查 screener-service 后重试。'
  if (status === 404) return '拆解接口不存在，当前图谱可能来自默认目录。请确认后端路由是否启用。'
  return '拆解接口连接异常，当前图谱可能是旧数据或默认目录。'
}

export interface ChainMethodSummary {
  title: string
  desc: string
  stats: Array<[string, string]>
}

export function chainMethodSummary(method: ChainMethod): ChainMethodSummary {
  // value_chain / competition 分支已随 Step4 overlay 化移除（两维度改为 overlay 开关，
  // 不再作为独立 method 入口）；method 当前恒为 'upstream_downstream'。
  void method
  return {
    title: '上下游拆解',
    desc: '从政策主题向上游材料、核心部件、制造设备、下游应用逐层展开，定位可跟踪节点和映射公司。',
    stats: [],
  }
}

// Convert ChainNode from API to BomNode for display (保留 overlay/transmission 标签)
export function chainNodeToBomNode(node: ChainNode, themeId: string): BomNode {
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
    transmission_layer: node.transmission_layer,
    transmission_layer_name: node.transmission_layer_name,
    value_chain: node.value_chain ? { note: '', ...node.value_chain } : undefined,
    competition: node.competition ? { note: '', ...node.competition } : undefined,
  }
}

// Recursively flatten ChainNode tree to BomNode array
export function flattenChainNodes(node: ChainNode, themeId: string, result: BomNode[] = []): BomNode[] {
  result.push(chainNodeToBomNode(node, themeId))
  if (node.children) {
    for (const child of node.children) {
      flattenChainNodes(child, themeId, result)
    }
  }
  return result
}

export const supplyChainTabs = [
  { key: 'policy', path: '/supply-chain-bom/policy', label: '政策梳理', subLabel: '政策证据' },
  { key: 'chain', path: '/supply-chain-bom', label: '产业链解构', subLabel: '三种模式' },
  { key: 'company', path: '/supply-chain-bom/company', label: '多维度分析', subLabel: '公司对比' },
  { key: 'ranking', path: '/supply-chain-bom/ranking', label: '候选总榜', subLabel: '真实排序' },
  { key: 'capex-review', path: '/supply-chain-bom/capex-review', label: 'CAPEX审核', subLabel: '证据入库' },
]

export function activeSupplyChainTab(pathname: string) {
  if (pathname.startsWith('/supply-chain-bom/policy')) return 'policy'
  if (pathname.startsWith('/supply-chain-bom/company')) return 'company'
  if (pathname.startsWith('/supply-chain-bom/ranking')) return 'ranking'
  if (pathname.startsWith('/supply-chain-bom/capex-review')) return 'capex-review'
  return 'chain'
}
