import { Col, Empty, Row, Space, Statistic, Tag, Typography } from 'antd'
import type { BomNode, SelectedNodeThesis } from './types'

const { Paragraph, Text } = Typography

interface NodeThesisPanelProps {
  node?: BomNode
  thesis?: SelectedNodeThesis
  candidateCount: number
  evidenceCount: number
  policyWeight: number
}

export default function NodeThesisPanel({ node, thesis = {}, candidateCount, evidenceCount, policyWeight }: NodeThesisPanelProps) {
  if (!node && !thesis.node_id) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="请选择BOM节点" />
  }

  const keywords = thesis.keywords || node?.keywords || []
  const triggerConditions = thesis.trigger_conditions || []
  const riskFactors = thesis.risk_factors || []

  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Space wrap>
        {node?.level && <Tag color="processing">{node.level}</Tag>}
        {node?.node_type && <Tag>{node.node_type}</Tag>}
        {(thesis.policy_theme || node?.policy_theme) && <Tag color="green">{thesis.policy_theme || node?.policy_theme}</Tag>}
      </Space>
      <Text strong>{thesis.name || node?.name || 'BOM节点'}</Text>
      <Paragraph type="secondary" style={{ marginBottom: 0 }}>
        {thesis.thesis || '选择节点后查看产业链拆解逻辑、触发条件与风险。'}
      </Paragraph>
      <Text type="secondary">{(thesis.bom_path || node?.bom_path || []).join(' / ')}</Text>
      <Space wrap>{keywords.map(keyword => <Tag key={keyword}>{keyword}</Tag>)}</Space>
      {thesis.mapping_message && (
        <Tag color={thesis.mapping_status === 'missing_company_mapping' ? 'orange' : 'blue'}>{thesis.mapping_message}</Tag>
      )}
      {!!triggerConditions.length && (
        <Space direction="vertical" size={4}>
          <Text strong>爆发触发条件</Text>
          <Space wrap>{triggerConditions.map(item => <Tag key={item} color="red">{item}</Tag>)}</Space>
        </Space>
      )}
      {!!riskFactors.length && (
        <Space direction="vertical" size={4}>
          <Text strong>主要风险</Text>
          <Space wrap>{riskFactors.map(item => <Tag key={item}>{item}</Tag>)}</Space>
        </Space>
      )}
      <Row gutter={12}>
        <Col span={8}><Statistic title="企业映射" value={candidateCount} /></Col>
        <Col span={8}><Statistic title="证据" value={evidenceCount} /></Col>
        <Col span={8}><Statistic title="权重" value={policyWeight} precision={2} /></Col>
      </Row>
    </Space>
  )
}
