import { Alert, Card, Empty, List, Space, Tag, Typography } from 'antd'
import type { EvidenceChainResponse } from '../../api/client'

const { Text, Paragraph } = Typography

function sourceColor(level?: string) {
  if (level === 'strong') return 'green'
  if (level === 'mid') return 'blue'
  if (level === 'weak') return 'orange'
  return 'default'
}

function statusColor(status?: string) {
  if (status === 'confirmed' || status === 'approved') return 'green'
  if (status === 'pending_review') return 'gold'
  if (status === 'rejected') return 'red'
  return 'default'
}

interface EvidenceChainPanelProps {
  evidenceChain: EvidenceChainResponse | null
}

export default function EvidenceChainPanel({ evidenceChain }: EvidenceChainPanelProps) {
  if (!evidenceChain) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无证据链数据" />
  }

  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      {evidenceChain.limitations?.length ? (
        <Alert
          type="warning"
          showIcon
          message="证据链限制"
          description={evidenceChain.limitations.join('；')}
        />
      ) : null}

      <Card size="small" title="业务标签证据">
        {evidenceChain.facts.length ? (
          <List
            size="small"
            dataSource={evidenceChain.facts}
            renderItem={(fact) => (
              <List.Item>
                <Space direction="vertical" size={4} style={{ width: '100%' }}>
                  <Space wrap>
                    <Tag color={sourceColor(fact.source_level)}>{fact.source_level || 'unknown'}</Tag>
                    <Tag color={statusColor(fact.validation_status)}>{fact.validation_status || '待复核'}</Tag>
                    <Tag>{fact.research_stage_signal || '--'} / {fact.commercial_stage_signal || '--'}</Tag>
                    {fact.confidence !== undefined ? <Tag>置信 {Number(fact.confidence).toFixed(2)}</Tag> : null}
                    {fact.growth_signal ? <Tag color="cyan">增长</Tag> : null}
                    {fact.profit_signal ? <Tag color="purple">盈利</Tag> : null}
                    {fact.moat_signal ? <Tag color="magenta">围墙</Tag> : null}
                  </Space>
                  <Paragraph style={{ marginBottom: 0 }}>{fact.original_quote || fact.fact_value || fact.fact_type || '--'}</Paragraph>
                  <Text type="secondary">{fact.created_at || '--'}</Text>
                </Space>
              </List.Item>
            )}
          />
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="该标签暂无结构化事实" />
        )}
      </Card>

      <Card size="small" title="来源文档">
        {evidenceChain.documents.length ? (
          <List
            size="small"
            dataSource={evidenceChain.documents}
            renderItem={(doc) => (
              <List.Item>
                <Space direction="vertical" size={2}>
                  <Space wrap>
                    <Text strong>{doc.title || doc.doc_id}</Text>
                    <Tag color={sourceColor(doc.source_level)}>
                      {doc.source_level || 'unknown'}
                    </Tag>
                  </Space>
                  <Text type="secondary">{doc.source_id || doc.source_type || '--'} · {doc.publish_time || doc.crawl_time || '--'}</Text>
                </Space>
              </List.Item>
            )}
          />
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无来源文档" />
        )}
      </Card>
    </Space>
  )
}
