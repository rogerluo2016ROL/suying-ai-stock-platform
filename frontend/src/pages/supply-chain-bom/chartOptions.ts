// P2-09: ECharts Tree option builders for Supply Chain BOM drill-down visualization
// Pure functions following the pattern from diagnosis/chartOptions.ts

import type { EChartsOption } from 'echarts'
import type { BomNode, ThemeRow, CandidateCompany } from './types'

// ─────────────────────────────────────────────────────────────────
// Bubble Chart Types for 三因子气泡图
// ─────────────────────────────────────────────────────────────────

/**
 * 三因子气泡图数据点
 * xAxis = 政策强度 (0-5)
 * yAxis = 业绩兑现 (0-20)
 * symbolSize = 评分大小
 * color = 共振等级 (强启动/启动/观察/观望)
 */
export interface BubbleDataPoint {
  /** 股票代码 */
  code: string
  /** 股票名称 */
  name: string
  /** 政策强度评分 (xAxis, 0-5) */
  policyIntensity: number
  /** 业绩兑现评分 (yAxis, 0-20) */
  performanceProof: number
  /** 综合评分 (symbolSize) */
  score: number
  /** 共振等级 (visualMap color) */
  resonanceLevel: '强启动' | '启动' | '观察' | '观望'
  /** 共振等级数值 (0-3) for visualMap dimension */
  resonanceValue: number
  /** 行业 */
  industry?: string
  /** 卡脖子评分 */
  chokepointScore?: number
  /** 产业周期阶段 */
  industryCycleStage?: string
  /** 商业化说明 */
  commercializationNote?: string
  /** 原始候选数据（tooltip详情） */
  raw?: CandidateCompany
}

/**
 * 从CandidateCompany提取气泡图数据点
 */
export function candidateToBubblePoint(candidate: CandidateCompany): BubbleDataPoint {
  // 从dimension_scores提取三因子
  const dimScores = candidate.dimension_scores || {}

  // 政策强度: 优先取 policy_intensity, 否则从 resonance 推断
  const policyIntensity = dimScores.policy_intensity ??
    (candidate.resonance?.policy_intensity ? parseInt(candidate.resonance.policy_intensity) : 0) ?? 0

  // 业绩兑现: 优先取 performance_proof, 否则从 resonance 推断
  const performanceProof = dimScores.performance_proof ??
    (candidate.resonance?.performance_proof ? parseInt(candidate.resonance.performance_proof) : 0) ?? 0

  // 综合评分
  const score = candidate.score ?? 0

  // 共振等级判定
  const tradeSignal = candidate.trade_signal || candidate.resonance?.signal || ''
  let resonanceLevel: BubbleDataPoint['resonanceLevel'] = '观望'
  let resonanceValue = 0
  if (tradeSignal.includes('强启动')) {
    resonanceLevel = '强启动'
    resonanceValue = 3
  } else if (tradeSignal.includes('启动')) {
    resonanceLevel = '启动'
    resonanceValue = 2
  } else if (tradeSignal.includes('观察') || score >= 12) {
    resonanceLevel = '观察'
    resonanceValue = 1
  }

  return {
    code: candidate.code,
    name: candidate.name || candidate.code,
    policyIntensity: Math.min(5, Math.max(0, policyIntensity)),
    performanceProof: Math.min(20, Math.max(0, performanceProof)),
    score,
    resonanceLevel,
    resonanceValue,
    industry: candidate.industry,
    chokepointScore: candidate.rating ? parseInt(candidate.rating) : undefined,
    industryCycleStage: candidate.commercialization_stage,
    commercializationNote: candidate.selection_reason,
    raw: candidate,
  }
}

// 共振等级颜色映射
const RESONANCE_COLORS: Record<BubbleDataPoint['resonanceLevel'], string> = {
  '强启动': '#ff4d4f',   // 红色 - 高共振爆发信号
  '启动': '#fa8c16',     // 橙色 - 启动信号
  '观察': '#1677ff',     // 蓝色 - 需持续观察
  '观望': '#8c8c8c',     // 灰色 - 暂不建议
}

/**
 * 构建三因子气泡图 ECharts Option
 * @param data 气泡数据点列表
 * @param dark 是否暗色模式
 */
export function buildBubbleOption(
  data: BubbleDataPoint[],
  dark = false,
): EChartsOption {
  const textColor = dark ? '#e0e0e0' : '#333'
  const bgColor = dark ? '#1f1f1f' : '#fff'

  // 转换为ECharts scatter数据格式: [x, y, resonanceValue, score]
  // dimension 0 = x (policyIntensity)
  // dimension 1 = y (performanceProof)
  // dimension 2 = resonanceValue (for visualMap color)
  // dimension 3 = score (for symbolSize)
  const scatterData = data.map(point => ({
    value: [point.policyIntensity, point.performanceProof, point.resonanceValue, point.score],
    name: point.name,
    code: point.code,
    itemStyle: {
      color: RESONANCE_COLORS[point.resonanceLevel],
    },
  }))

  return {
    backgroundColor: bgColor,
    title: {
      text: '三因子共振气泡图',
      subtext: '横轴: 政策强度 | 纵轴: 业绩兑现 | 大小: 评分 | 颜色: 共振等级',
      left: 'center',
      textStyle: {
        color: textColor,
        fontSize: 16,
      },
      subtextStyle: {
        color: dark ? '#999' : '#666',
        fontSize: 12,
      },
    },
    tooltip: {
      trigger: 'item',
      formatter: (params: unknown) => {
        const p = params as { data?: { value?: number[]; name?: string; code?: string } }
        const val = p.data?.value || []
        const point = data.find(d => d.code === p.data?.code)
        if (!point) return ''

        const policyIntensity = val[0]?.toFixed(1) ?? '0'
        const performanceProof = val[1]?.toFixed(1) ?? '0'
        const scoreNum = val[3] ?? 0
        const score = scoreNum.toFixed(1)

        let html = `
          <div style="font-weight:bold;margin-bottom:4px;font-size:14px">
            ${point.name} (${point.code})
          </div>
          <div style="margin-bottom:6px;padding:4px 8px;background:${RESONANCE_COLORS[point.resonanceLevel]}20;border-radius:4px">
            <span style="color:${RESONANCE_COLORS[point.resonanceLevel]};font-weight:600">
              ${point.resonanceLevel}
            </span>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;font-size:12px">
            <div>政策强度: <b>${policyIntensity}</b>/5</div>
            <div>业绩兑现: <b>${performanceProof}</b>/20</div>
            <div>综合评分: <b style="color:${scoreNum >= 16 ? '#ff4d4f' : scoreNum >= 12 ? '#fa8c16' : '#1677ff'}">${score}</b></div>
            <div>产业周期: ${point.industryCycleStage || '--'}</div>
          </div>
        `
        if (point.chokepointScore) {
          html += `<div style="margin-top:4px;font-size:12px">卡脖子评分: ${point.chokepointScore}</div>`
        }
        if (point.commercializationNote) {
          html += `<div style="margin-top:4px;font-size:11px;color:#666">${point.commercializationNote}</div>`
        }
        return html
      },
    },
    grid: {
      left: '8%',
      right: '12%',
      bottom: '12%',
      top: '18%',
      containLabel: true,
    },
    xAxis: {
      type: 'value',
      name: '政策强度',
      nameLocation: 'middle',
      nameGap: 30,
      nameTextStyle: {
        color: textColor,
        fontSize: 12,
      },
      min: 0,
      max: 5,
      interval: 1,
      axisLine: {
        lineStyle: { color: dark ? '#444' : '#d9d9d9' },
      },
      axisLabel: {
        color: textColor,
        formatter: (val: number) => {
          const labels: Record<number, string> = { 0: '无', 1: '弱', 2: '中', 3: '强', 4: '很强', 5: '极强' }
          return labels[val] ?? String(val)
        },
      },
      splitLine: {
        lineStyle: { color: dark ? '#333' : '#f0f0f0' },
      },
    },
    yAxis: {
      type: 'value',
      name: '业绩兑现',
      nameLocation: 'middle',
      nameGap: 40,
      nameTextStyle: {
        color: textColor,
        fontSize: 12,
      },
      min: 0,
      max: 20,
      interval: 5,
      axisLine: {
        lineStyle: { color: dark ? '#444' : '#d9d9d9' },
      },
      axisLabel: {
        color: textColor,
      },
      splitLine: {
        lineStyle: { color: dark ? '#333' : '#f0f0f0' },
      },
    },
    visualMap: {
      show: true,
      type: 'piecewise',
      dimension: 2, // resonanceValue dimension
      categories: ['观望', '观察', '启动', '强启动'],
      inRange: {
        color: ['#8c8c8c', '#1677ff', '#fa8c16', '#ff4d4f'],
      },
      outOfRange: {
        color: '#8c8c8c',
      },
      orient: 'vertical',
      right: 10,
      top: 'center',
      text: ['共振等级'],
      textStyle: {
        color: textColor,
      },
      pieces: [
        { value: 0, label: '观望', color: '#8c8c8c' },
        { value: 1, label: '观察', color: '#1677ff' },
        { value: 2, label: '启动', color: '#fa8c16' },
        { value: 3, label: '强启动', color: '#ff4d4f' },
      ],
    },
    series: [
      {
        type: 'scatter',
        name: '候选标的',
        data: scatterData,
        symbolSize: (val: number[]) => {
          // val[3] = score, 映射到气泡大小 10-60
          const score = val[3] || 0
          return Math.max(10, Math.min(60, 10 + score * 2))
        },
        itemStyle: {
          shadowBlur: 10,
          shadowColor: 'rgba(0, 0, 0, 0.3)',
          shadowOffsetY: 5,
          opacity: 0.8,
        },
        emphasis: {
          itemStyle: {
            shadowBlur: 20,
            shadowColor: 'rgba(0, 0, 0, 0.5)',
            opacity: 1,
            borderWidth: 2,
            borderColor: '#fff',
          },
          scale: 1.2,
        },
        animationDuration: 1000,
        animationEasing: 'elasticOut',
      },
    ],
  }
}

export interface TreeNode {
  name: string
  value?: number | string
  node_id: string
  chokepoint_level?: 'core' | 'critical' | 'normal'
  collapsed?: boolean
  itemStyle?: {
    color?: string
    borderColor?: string
    borderWidth?: number
  }
  label?: {
    show?: boolean
    fontSize?: number
    color?: string
  }
  children?: TreeNode[]
}

export interface ChainTreeData {
  themes: ThemeRow[]
  nodes: BomNode[]
}

// Color mapping based on chokepoint level
const CHOKEPOINT_COLORS: Record<string, string> = {
  core: '#ff4d4f',     // red - 卡脖子核心
  critical: '#faad14', // gold - 关键环节
  normal: '#1677ff',   // blue - 普通
}

// SymbolSize mapping based on chokepoint level
const CHOKEPOINT_SYMBOL_SIZE: Record<string, number> = {
  core: 16,     // 核心=16
  critical: 12, // 关键=12
  normal: 8,    // 普通=8
}

/**
 * Determine chokepoint level from node properties
 * Can be customized based on actual node_type, level, or other fields
 */
function getChokepointLevel(node: BomNode): 'core' | 'critical' | 'normal' {
  // Infer from node_type or level - can be adjusted based on actual data
  const nodeType = (node.node_type || '').toLowerCase()
  const level = (node.level || '').toLowerCase()

  // Core chokepoint nodes
  if (nodeType.includes('核心') || nodeType.includes('key') || level.includes('l1') || level.includes('tier1')) {
    return 'core'
  }
  // Critical nodes
  if (nodeType.includes('关键') || nodeType.includes('critical') || level.includes('l2') || level.includes('tier2')) {
    return 'critical'
  }
  // Normal nodes
  return 'normal'
}

/**
 * Build a tree node from a BomNode
 */
function buildTreeNode(node: BomNode, allNodes: BomNode[]): TreeNode {
  const chokepointLevel = getChokepointLevel(node)
  const color = CHOKEPOINT_COLORS[chokepointLevel]

  // Find children based on child_node_ids
  const children = (node.child_node_ids || [])
    .map(childId => allNodes.find(n => n.node_id === childId))
    .filter(Boolean)
    .map(childNode => buildTreeNode(childNode!, allNodes))

  return {
    name: node.name,
    value: node.policy_theme || node.level,
    node_id: node.node_id,
    chokepoint_level: chokepointLevel,
    itemStyle: {
      color,
      borderColor: '#fff',
      borderWidth: 1,
    },
    label: {
      show: true,
      fontSize: 11,
      color: '#333',
    },
    children: children.length > 0 ? children : undefined,
  }
}

/**
 * Build ECharts Tree option from chain data
 * Supports depth=3 hierarchical rendering with drill-down capability
 */
export function buildChainTreeOption(
  data: ChainTreeData,
  dark = false,
): EChartsOption {
  const textColor = dark ? '#e0e0e0' : '#333'
  const borderColor = dark ? '#444' : '#d9d9d9'

  // Build tree structure from themes and nodes
  const treeData: TreeNode[] = data.themes.map(theme => {
    // Get nodes for this theme
    const themeNodes = data.nodes.filter(n => n.theme_id === theme.theme_id)

    // Find root nodes (nodes without parent_node_id or parent_node_id is null)
    const rootNodes = themeNodes.filter(n => !n.parent_node_id)

    // Build children for each root node
    const children = rootNodes.map(rootNode => buildTreeNode(rootNode, themeNodes))

    return {
      name: theme.name,
      value: theme.policy_weight,
      node_id: theme.theme_id,
      chokepoint_level: 'normal',
      itemStyle: {
        color: '#52c41a', // Theme root node - green
        borderColor: '#fff',
        borderWidth: 2,
      },
      label: {
        show: true,
        fontSize: 13,
        color: textColor,
      },
      children,
    }
  })

  return {
    tooltip: {
      trigger: 'item',
      triggerOn: 'mousemove|click',
      formatter: (params: unknown) => {
        const p = params as { data?: TreeNode }
        const nodeData = p.data
        if (!nodeData) return ''
        let html = `<div style="font-weight:bold;margin-bottom:4px">${nodeData.name}</div>`
        if (nodeData.chokepoint_level) {
          const levelLabel = nodeData.chokepoint_level === 'core' ? '卡脖子核心'
            : nodeData.chokepoint_level === 'critical' ? '关键环节'
            : '普通环节'
          const levelColor = CHOKEPOINT_COLORS[nodeData.chokepoint_level]
          html += `<div><span style="color:${levelColor}">${levelLabel}</span></div>`
        }
        if (nodeData.value) {
          html += `<div style="color:#666">${nodeData.value}</div>`
        }
        return html
      },
    },
    series: [
      {
        type: 'tree',
        data: treeData,
        name: '产业链',
        top: '5%',
        left: '10%',
        bottom: '5%',
        right: '20%',
        symbolSize: (_value: number, params: unknown) => {
          const p = params as { data?: TreeNode }
          const nodeData = p.data
          return CHOKEPOINT_SYMBOL_SIZE[nodeData?.chokepoint_level || 'normal']
        },
        symbol: 'circle',
        orient: 'LR', // Left to Right layout for better drill-down experience
        expandAndCollapse: true,
        initialTreeDepth: 3, // Render depth=3 levels
        label: {
          position: 'right',
          verticalAlign: 'middle',
          align: 'left',
          fontSize: 11,
          color: textColor,
        },
        leaves: {
          label: {
            position: 'right',
            verticalAlign: 'middle',
            align: 'left',
          },
        },
        lineStyle: {
          color: borderColor,
          width: 1.2,
          curveness: 0.5,
        },
        itemStyle: {
          borderWidth: 1,
          borderColor: '#fff',
        },
        emphasis: {
          focus: 'descendant',
          itemStyle: {
            borderWidth: 2,
            borderColor: '#1677ff',
          },
          lineStyle: {
            width: 2,
          },
        },
        animationDuration: 400,
        animationDurationUpdate: 400,
      },
    ],
  }
}

/**
 * Build a simplified tree option for single theme drill-down
 * Used when user clicks on a specific theme to drill into its nodes
 */
export function buildThemeTreeOption(
  theme: ThemeRow,
  nodes: BomNode[],
  dark = false,
): EChartsOption {
  const themeNodes = nodes.filter(n => n.theme_id === theme.theme_id)
  const rootNodes = themeNodes.filter(n => !n.parent_node_id)

  const treeData: TreeNode[] = rootNodes.map(rootNode =>
    buildTreeNode(rootNode, themeNodes),
  )

  return {
    tooltip: {
      trigger: 'item',
      triggerOn: 'mousemove|click',
      formatter: (params: unknown) => {
        const p = params as { data?: TreeNode }
        const nodeData = p.data
        if (!nodeData) return ''
        let html = `<div style="font-weight:bold;margin-bottom:4px">${nodeData.name}</div>`
        if (nodeData.chokepoint_level) {
          const levelLabel = nodeData.chokepoint_level === 'core' ? '卡脖子核心'
            : nodeData.chokepoint_level === 'critical' ? '关键环节'
            : '普通环节'
          const levelColor = CHOKEPOINT_COLORS[nodeData.chokepoint_level]
          html += `<div><span style="color:${levelColor}">${levelLabel}</span></div>`
        }
        return html
      },
    },
    series: [
      {
        type: 'tree',
        data: treeData,
        name: theme.name,
        top: '8%',
        left: '10%',
        bottom: '8%',
        right: '15%',
        symbolSize: (_value: number, params: unknown) => {
          const p = params as { data?: TreeNode }
          const nodeData = p.data
          return CHOKEPOINT_SYMBOL_SIZE[nodeData?.chokepoint_level || 'normal']
        },
        symbol: 'circle',
        orient: 'LR',
        expandAndCollapse: true,
        initialTreeDepth: 3,
        label: {
          position: 'right',
          verticalAlign: 'middle',
          align: 'left',
          fontSize: 11,
        },
        leaves: {
          label: {
            position: 'right',
            verticalAlign: 'middle',
            align: 'left',
          },
        },
        lineStyle: {
          color: '#d9d9d9',
          width: 1.2,
          curveness: 0.5,
        },
        emphasis: {
          focus: 'descendant',
        },
        animationDuration: 400,
        animationDurationUpdate: 400,
      },
    ],
  }
}