// BOM 节点表 + 当前节点研究上下文（第二行区块）
// 从 SupplyChainBom.tsx 拆出，nodeColumns 列定义随 UI 下沉

import { Button, Col, Row, Space, Table, Tag, Typography } from 'antd'
import type { TableColumnsType } from 'antd'
import { EyeOutlined } from '@ant-design/icons'
import NodeThesisPanel from './NodeThesisPanel'
import NodeOverlayTags from './NodeOverlayTags'
import type { ChainOverlay } from './MethodSelector'
import type { BomNode, SelectedNodeThesis, ThemeRow } from './types'
import { lightTokens } from '../../styles/tokens'

const { Text } = Typography

interface NodeResearchSectionProps {
  nodes: BomNode[]
  selectedNode?: BomNode
  selectedNodeThesis: SelectedNodeThesis
  selectedTheme?: ThemeRow
  candidateCount: number
  nodeDetail: any
  chainOverlays: ChainOverlay[]
  onSelectNode: (node: BomNode) => void
}

export default function NodeResearchSection({
  nodes,
  selectedNode,
  selectedNodeThesis,
  selectedTheme,
  candidateCount,
  nodeDetail,
  chainOverlays,
  onSelectNode,
}: NodeResearchSectionProps) {
  const nodeColumns: TableColumnsType<BomNode> = [
    {
      title: 'BOM节点',
      dataIndex: 'name',
      render: (_: string, row: BomNode) => (
        <Button type="link" icon={<EyeOutlined />} onClick={() => onSelectNode(row)}>
          {row.name}
        </Button>
      ),
    },
    { title: '层级', dataIndex: 'level', width: 86, render: (v: string) => <Tag>{v}</Tag> },
    { title: '类型', dataIndex: 'node_type', width: 94 },
    {
      title: '维度标签',
      key: 'overlay_tags',
      width: 260,
      render: (_: unknown, row: BomNode) => <NodeOverlayTags node={row} overlays={chainOverlays} />,
    },
  ]

  return (
    <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
      <Col xs={24} xl={14}>
        <Table
          rowKey="node_id"
          size="small"
          columns={nodeColumns}
          dataSource={nodes}
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
              candidateCount={candidateCount}
              evidenceCount={nodeDetail?.evidence?.length || 0}
              policyWeight={selectedTheme?.policy_weight || 1}
            />
          </Space>
        </div>
      </Col>
    </Row>
  )
}
