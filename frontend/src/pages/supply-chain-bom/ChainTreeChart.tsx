// P2-09: ECharts Tree drill-down chart component for supply chain BOM visualization
// Replaces Antd Tree with better visual drill-down experience

import { useMemo } from 'react'
import ReactECharts from 'echarts-for-react'
import { buildChainTreeOption, buildThemeTreeOption } from './chartOptions'
import type { BomNode, ThemeRow } from './types'

interface ChainTreeChartProps {
  themes: ThemeRow[]
  nodes: BomNode[]
  selectedThemeId?: string
  selectedNodeId?: string
  onNodeClick?: (node: BomNode) => void
  onThemeClick?: (theme: ThemeRow) => void
  dark?: boolean
  height?: number
}

export default function ChainTreeChart({
  themes,
  nodes,
  selectedThemeId,
  selectedNodeId,
  onNodeClick,
  onThemeClick,
  dark = false,
  height = 360,
}: ChainTreeChartProps) {
  // Build tree option - either full view or drill-down view for selected theme
  const treeOption = useMemo(() => {
    if (selectedThemeId) {
      const selectedTheme = themes.find(t => t.theme_id === selectedThemeId)
      if (selectedTheme) {
        // Drill-down view for selected theme
        return buildThemeTreeOption(selectedTheme, nodes, dark)
      }
    }
    // Full view showing all themes as root nodes
    return buildChainTreeOption({ themes, nodes }, dark)
  }, [themes, nodes, selectedThemeId, dark])

  // Handle click events on tree nodes
  const handleEvents = useMemo(() => ({
    click: (params: unknown) => {
      const p = params as {
        data?: { node_id?: string; name?: string }
        dataType?: string
      }
      const nodeData = p.data
      if (!nodeData?.node_id) return

      // Check if clicked on a theme (theme_id matches theme, not node)
      const clickedTheme = themes.find(t => t.theme_id === nodeData.node_id)
      if (clickedTheme && onThemeClick) {
        onThemeClick(clickedTheme)
        return
      }

      // Check if clicked on a node
      const clickedNode = nodes.find(n => n.node_id === nodeData.node_id)
      if (clickedNode && onNodeClick) {
        onNodeClick(clickedNode)
      }
    },
  }), [themes, nodes, onNodeClick, onThemeClick])

  return (
    <div style={{ height, border: '1px solid #f0f0f0', borderRadius: 8, background: dark ? '#1f1f1f' : '#fff' }}>
      <ReactECharts
        option={treeOption}
        style={{ height: height - 2 }}
        onEvents={handleEvents}
        opts={{ renderer: 'canvas' }}
      />
    </div>
  )
}