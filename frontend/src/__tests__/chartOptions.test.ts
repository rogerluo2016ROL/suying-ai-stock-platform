// P2-09: Unit tests for ChainTreeChart component and chartOptions builders
import { describe, it, expect } from 'vitest'
import { buildChainTreeOption, buildThemeTreeOption } from '../pages/supply-chain-bom/chartOptions'
import type { BomNode, ThemeRow } from '../pages/supply-chain-bom/types'

const firstSeries = (option: ReturnType<typeof buildChainTreeOption> | ReturnType<typeof buildThemeTreeOption>) => {
  const series = option.series
  if (!Array.isArray(series)) {
    throw new Error('Expected chart option series to be an array')
  }
  return series[0] as any
}

// Mock data for testing
const mockThemes: ThemeRow[] = [
  {
    theme_id: 'theme-1',
    name: '半导体产业链',
    policy_weight: 0.5,
    keywords: ['芯片', '半导体'],
    node_count: 3,
  },
  {
    theme_id: 'theme-2',
    name: '新能源产业链',
    policy_weight: 0.3,
    keywords: ['电池', '新能源'],
    node_count: 2,
  },
]

const mockNodes: BomNode[] = [
  {
    node_id: 'node-1',
    theme_id: 'theme-1',
    chain_id: 'chain-1',
    parent_node_id: null,
    child_node_ids: ['node-2', 'node-3'],
    level: 'L1',
    name: '芯片设计',
    node_type: '核心',
    keywords: ['设计', 'EDA'],
    policy_theme: '半导体自主可控',
  },
  {
    node_id: 'node-2',
    theme_id: 'theme-1',
    chain_id: 'chain-1',
    parent_node_id: 'node-1',
    child_node_ids: [],
    level: 'L2',
    name: 'EDA工具',
    node_type: '关键',
    keywords: ['EDA', '软件'],
    policy_theme: '半导体自主可控',
  },
  {
    node_id: 'node-3',
    theme_id: 'theme-1',
    chain_id: 'chain-1',
    parent_node_id: 'node-1',
    child_node_ids: [],
    level: 'L3',
    name: 'IP核',
    node_type: '普通',
    keywords: ['IP', '核'],
    policy_theme: '半导体自主可控',
  },
  {
    node_id: 'node-4',
    theme_id: 'theme-2',
    chain_id: 'chain-2',
    parent_node_id: null,
    child_node_ids: ['node-5'],
    level: 'L1',
    name: '锂电池',
    node_type: '核心',
    keywords: ['电池', '锂'],
    policy_theme: '新能源',
  },
  {
    node_id: 'node-5',
    theme_id: 'theme-2',
    chain_id: 'chain-2',
    parent_node_id: 'node-4',
    child_node_ids: [],
    level: 'L2',
    name: '正极材料',
    node_type: '关键',
    keywords: ['正极', '材料'],
    policy_theme: '新能源',
  },
]

describe('chartOptions', () => {
  describe('buildChainTreeOption', () => {
    it('should return valid ECharts option structure', () => {
      const option = buildChainTreeOption({ themes: mockThemes, nodes: mockNodes })

      expect(option).toHaveProperty('tooltip')
      expect(option).toHaveProperty('series')
      expect(option.series).toHaveLength(1)
      expect(firstSeries(option).type).toBe('tree')
    })

    it('should build tree data with themes as root nodes', () => {
      const option = buildChainTreeOption({ themes: mockThemes, nodes: mockNodes })
      const treeData = firstSeries(option).data

      expect(treeData).toHaveLength(2)
      expect(treeData[0].name).toBe('半导体产业链')
      expect(treeData[1].name).toBe('新能源产业链')
    })

    it('should include children nodes under each theme', () => {
      const option = buildChainTreeOption({ themes: mockThemes, nodes: mockNodes })
      const semiconTheme = firstSeries(option).data[0]

      expect(semiconTheme.children).toBeDefined()
      expect(semiconTheme.children.length).toBeGreaterThan(0)
    })

    it('should set initialTreeDepth to 3', () => {
      const option = buildChainTreeOption({ themes: mockThemes, nodes: mockNodes })

      expect(firstSeries(option).initialTreeDepth).toBe(3)
    })

    it('should use LR (left-to-right) orient for drill-down', () => {
      const option = buildChainTreeOption({ themes: mockThemes, nodes: mockNodes })

      expect(firstSeries(option).orient).toBe('LR')
    })

    it('should apply dark mode colors when dark=true', () => {
      const darkOption = buildChainTreeOption({ themes: mockThemes, nodes: mockNodes }, true)
      const lightOption = buildChainTreeOption({ themes: mockThemes, nodes: mockNodes }, false)

      // Dark mode should have different text color
      expect(firstSeries(darkOption).label.color).toBe('#e0e0e0')
      expect(firstSeries(lightOption).label.color).toBe('#333')
    })
  })

  describe('buildThemeTreeOption', () => {
    it('should return valid ECharts option for single theme', () => {
      const theme = mockThemes[0]
      const option = buildThemeTreeOption(theme, mockNodes)

      expect(option).toHaveProperty('tooltip')
      expect(option).toHaveProperty('series')
      expect(firstSeries(option).type).toBe('tree')
    })

    it('should only include nodes from the selected theme', () => {
      const theme = mockThemes[0] // 半导体产业链
      const option = buildThemeTreeOption(theme, mockNodes)
      const treeData = firstSeries(option).data

      // All nodes should belong to theme-1
      const allNodeIds: string[] = []
      const collectIds = (nodes: any[]) => {
        nodes.forEach(n => {
          allNodeIds.push(n.node_id)
          if (n.children) collectIds(n.children)
        })
      }
      collectIds(treeData)

      // Node IDs should all be from theme-1 (node-1, node-2, node-3)
      expect(allNodeIds.every(id => ['node-1', 'node-2', 'node-3', 'theme-1'].includes(id))).toBe(true)
    })
  })

  describe('chokepoint level mapping', () => {
    it('should assign core level to nodes with node_type containing 核心', () => {
      const option = buildChainTreeOption({ themes: mockThemes, nodes: mockNodes })
      const treeData = firstSeries(option).data

      // Find chip design node (node_type: '核心')
      const findNode = (nodes: any[], name: string): any => {
        for (const n of nodes) {
          if (n.name === name) return n
          if (n.children) {
            const found = findNode(n.children, name)
            if (found) return found
          }
        }
        return null
      }

      const chipDesignNode = findNode(treeData, '芯片设计')
      expect(chipDesignNode).toBeDefined()
      expect(chipDesignNode.chokepoint_level).toBe('core')
    })

    it('should use symbolSize function that returns correct sizes for levels', () => {
      const option = buildChainTreeOption({ themes: mockThemes, nodes: mockNodes })
      const symbolSizeFn = firstSeries(option).symbolSize as Function

      // Test with mock params
      const coreNode = { data: { chokepoint_level: 'core' } }
      const criticalNode = { data: { chokepoint_level: 'critical' } }
      const normalNode = { data: { chokepoint_level: 'normal' } }

      expect(symbolSizeFn(0, coreNode)).toBe(16)
      expect(symbolSizeFn(0, criticalNode)).toBe(12)
      expect(symbolSizeFn(0, normalNode)).toBe(8)
    })
  })
})

// Test ChainTreeChart component rendering (integration test)
describe('ChainTreeChart component', () => {
  it('should be importable', async () => {
    const { default: ChainTreeChart } = await import('../pages/supply-chain-bom/ChainTreeChart')
    expect(ChainTreeChart).toBeDefined()
    expect(typeof ChainTreeChart).toBe('function')
  })
})
