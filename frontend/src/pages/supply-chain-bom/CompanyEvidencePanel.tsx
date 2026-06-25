import { Button, Descriptions, Empty, Progress, Space, Tabs, Tag, Typography } from 'antd'
import { CheckCircleOutlined, CloseCircleOutlined, WarningOutlined } from '@ant-design/icons'
import type { CandidateCompany } from './types'
import { dimensionLabel, formatNumber } from './formatters'

const { Text } = Typography

interface CompanyEvidencePanelProps {
  company: CandidateCompany | null
  loading?: boolean
  onReview?: (code: string, nodeId: string, decision: 'verified' | 'rejected' | 'needs_more_evidence') => Promise<void> | void
}

export default function CompanyEvidencePanel({ company, onReview }: CompanyEvidencePanelProps) {
  if (!company) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="请选择候选公司查看证据" />
  }

  const nodeId = company.node_id || ''
  const financial = company.financial_indicators || {}
  const dimensionEntries = Object.entries(company.dimension_scores || {})
  const canReview = Boolean(company.code && nodeId)

  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Space style={{ justifyContent: 'space-between', width: '100%' }}>
        <Space direction="vertical" size={2}>
          <Text strong>{company.name || company.code}</Text>
          <Text type="secondary">{company.code}</Text>
        </Space>
        <Tag color={company.mapping_status === 'verified' ? 'green' : 'gold'}>
          {company.mapping_status || 'pending_review'}
        </Tag>
      </Space>
      <Tabs
        items={[
          {
            key: 'evidence',
            label: '证据链',
            children: (
              <Space direction="vertical" size={10} style={{ width: '100%' }}>
                <Descriptions column={1} size="small" bordered>
                  <Descriptions.Item label="映射节点">{company.node_name || company.layer || '--'}</Descriptions.Item>
                  <Descriptions.Item label="置信度">{formatNumber(company.mapping_confidence, 2)}</Descriptions.Item>
                  <Descriptions.Item label="来源">{company.mapping_source || '--'}</Descriptions.Item>
                  <Descriptions.Item label="产品">{company.products?.join('、') || '--'}</Descriptions.Item>
                </Descriptions>
                <Space wrap>
                  {(company.moat_evidence || []).map((item, index) => (
                    <Tag key={`${item.summary}-${index}`} color="purple">{item.summary || item.evidence_type}</Tag>
                  ))}
                  {!(company.moat_evidence || []).length && <Tag>等待专利、客户、产能证据</Tag>}
                </Space>
                <Space wrap>
                  {(company.evidence_gaps || []).map(gap => <Tag key={gap} color="orange">{gap}</Tag>)}
                </Space>
              </Space>
            ),
          },
          {
            key: 'financial',
            label: '财务',
            children: (
              <Descriptions column={2} size="small" bordered>
                <Descriptions.Item label="收入增速">{formatNumber(financial.revenue_growth)}%</Descriptions.Item>
                <Descriptions.Item label="利润增速">{formatNumber(financial.profit_growth)}%</Descriptions.Item>
                <Descriptions.Item label="ROE">{formatNumber(financial.roe)}%</Descriptions.Item>
                <Descriptions.Item label="毛利率">{formatNumber(financial.gross_margin)}%</Descriptions.Item>
              </Descriptions>
            ),
          },
          {
            key: 'score',
            label: '评分',
            children: (
              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                {dimensionEntries.map(([key, value]) => (
                  <div key={key}>
                    <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                      <Text>{dimensionLabel[key] || key}</Text>
                      <Text>{formatNumber(value, 1)}</Text>
                    </Space>
                    <Progress percent={Math.min(100, Number(value) * 5)} showInfo={false} size="small" />
                  </div>
                ))}
                {!dimensionEntries.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无评分拆解" />}
              </Space>
            ),
          },
          {
            key: 'review',
            label: '复核',
            children: (
              <Space wrap>
                <Button type="primary" icon={<CheckCircleOutlined />} disabled={!canReview} onClick={() => onReview?.(company.code, nodeId, 'verified')}>确认</Button>
                <Button icon={<WarningOutlined />} disabled={!canReview} onClick={() => onReview?.(company.code, nodeId, 'needs_more_evidence')}>补证据</Button>
                <Button danger icon={<CloseCircleOutlined />} disabled={!canReview} onClick={() => onReview?.(company.code, nodeId, 'rejected')}>驳回</Button>
              </Space>
            ),
          },
        ]}
      />
    </Space>
  )
}
