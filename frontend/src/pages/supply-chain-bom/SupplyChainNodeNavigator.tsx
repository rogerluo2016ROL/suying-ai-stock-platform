import { Button, Empty, Space, Table, Tag, Typography } from 'antd'
import type { TableColumnsType } from 'antd'
import { ApartmentOutlined } from '@ant-design/icons'
import type { SupplyChainMappingQuality } from '../../api/client'
import type { BomNode, SelectedNodeThesis, ThemeRow } from './types'
import NodeThesisPanel from './NodeThesisPanel'

const { Text } = Typography

interface SupplyChainNodeNavigatorProps {
  themes: ThemeRow[]
  nodes: BomNode[]
  selectedThemeId: string
  selectedNodeId: string
  quality?: SupplyChainMappingQuality | null
  selectedNodeThesis: SelectedNodeThesis
  candidateCount: number
  evidenceCount: number
  onSelectTheme: (themeId: string) => void
  onSelectNode: (node: BomNode) => void
}

export default function SupplyChainNodeNavigator({
  themes,
  nodes,
  selectedThemeId,
  selectedNodeId,
  quality,
  selectedNodeThesis,
  candidateCount,
  evidenceCount,
  onSelectTheme,
  onSelectNode,
}: SupplyChainNodeNavigatorProps) {
  const pressureByNode = new Map((quality?.hotspot_nodes || []).map(item => [item.node_id, Number(item.review_pressure || 0)]))
  const filteredNodes = selectedThemeId ? nodes.filter(node => node.theme_id === selectedThemeId) : nodes
  const selectedTheme = themes.find(theme => theme.theme_id === selectedThemeId)
  const selectedNode = nodes.find(node => node.node_id === selectedNodeId)

  const columns: TableColumnsType<BomNode> = [
    {
      title: '节点',
      render: (_: unknown, row: BomNode) => (
        <Button type="link" icon={<ApartmentOutlined />} onClick={() => onSelectNode(row)}>
          {row.name}
        </Button>
      ),
    },
    {
      title: '压力',
      width: 136,
      render: (_: unknown, row: BomNode) => {
        const pressure = pressureByNode.get(row.node_id) || 0
        return pressure ? <Tag color="orange">待复核压力 {pressure}</Tag> : <Tag>低</Tag>
      },
    },
  ]

  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Space style={{ justifyContent: 'space-between', width: '100%' }}>
        <Text strong>产业链导航</Text>
        <Tag color="gold">待复核 {quality?.review_queue_count || 0}</Tag>
      </Space>
      <Space wrap>
        {themes.map(theme => (
          <Button
            key={theme.theme_id}
            size="small"
            type={theme.theme_id === selectedThemeId ? 'primary' : 'default'}
            onClick={() => onSelectTheme(theme.theme_id)}
          >
            {theme.name}
          </Button>
        ))}
      </Space>
      <Table
        rowKey="node_id"
        size="small"
        columns={columns}
        dataSource={filteredNodes}
        pagination={{ pageSize: 8, showSizeChanger: false }}
        rowClassName={row => row.node_id === selectedNodeId ? 'ant-table-row-selected' : ''}
        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无节点" /> }}
      />
      <NodeThesisPanel
        node={selectedNode}
        thesis={selectedNodeThesis}
        candidateCount={candidateCount}
        evidenceCount={evidenceCount}
        policyWeight={selectedTheme?.policy_weight || 1}
      />
    </Space>
  )
}
