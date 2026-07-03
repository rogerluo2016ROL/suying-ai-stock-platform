import { Card, Empty, List, Space, Tag, Timeline, Typography } from 'antd'
import type { EvidenceChainResponse } from '../../api/client'

const { Text, Paragraph } = Typography

function transitionColor(status?: string) {
  if (status === 'approved') return 'green'
  if (status === 'pending_review') return 'gold'
  if (status === 'rejected') return 'red'
  return 'blue'
}

interface StageTimelinePanelProps {
  evidenceChain: EvidenceChainResponse | null
}

export default function StageTimelinePanel({ evidenceChain }: StageTimelinePanelProps) {
  const transitions = evidenceChain?.stage_transitions || []
  const expectations = evidenceChain?.expectations || []
  const freshness = evidenceChain?.freshness && 'freshness_status' in evidenceChain.freshness
    ? evidenceChain.freshness
    : null

  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Card size="small" title="研发与商用阶段变化">
        {transitions.length ? (
          <Timeline
            items={transitions.map((item) => ({
              color: transitionColor(item.review_status),
              children: (
                <Space direction="vertical" size={4}>
                  <Space wrap>
                    <Tag>{item.old_research_stage || '--'} → {item.new_research_stage || '--'}</Tag>
                    <Tag>{item.old_commercial_stage || '--'} → {item.new_commercial_stage || '--'}</Tag>
                    <Tag color={transitionColor(item.review_status)}>{item.review_status || '待复核'}</Tag>
                  </Space>
                  <Paragraph style={{ marginBottom: 0 }}>{item.change_reason || item.trigger_fact_id || '--'}</Paragraph>
                  <Text type="secondary">{item.created_at || '--'}</Text>
                </Space>
              ),
            }))}
          />
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无阶段变化记录" />
        )}
      </Card>

      <Card size="small" title="预期差跟踪">
        {expectations.length ? (
          <List
            size="small"
            dataSource={expectations}
            renderItem={(item) => (
              <List.Item>
                <Space direction="vertical" size={4} style={{ width: '100%' }}>
                  <Space wrap>
                    <Tag color={item.gap_status === '兑现' ? 'green' : 'gold'}>{item.gap_status || 'pending'}</Tag>
                    <Tag>{item.claim_source_type || '--'}</Tag>
                    {item.expected_date ? <Tag>跟踪到 {item.expected_date}</Tag> : null}
                  </Space>
                  <Paragraph style={{ marginBottom: 0 }}>{item.claim_text || '--'}</Paragraph>
                  <Text type="secondary">预期：{item.expected_result || '--'}；实际：{item.actual_progress || '等待后续证据'}</Text>
                </Space>
              </List.Item>
            )}
          />
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无预期差跟踪项" />
        )}
      </Card>

      <Card size="small" title="证据新鲜度">
        {freshness ? (
          <Space wrap>
            <Tag color={freshness.freshness_status === 'fresh' ? 'green' : 'orange'}>
              {freshness.freshness_status || 'unknown'} · {freshness.days_since_update ?? '--'} 天
            </Tag>
            {freshness.last_strong_evidence_date ? <Tag>强证据 {freshness.last_strong_evidence_date}</Tag> : null}
            {freshness.last_mid_evidence_date ? <Tag>中证据 {freshness.last_mid_evidence_date}</Tag> : null}
            {freshness.next_review_date ? <Tag>下次复核 {freshness.next_review_date}</Tag> : null}
          </Space>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无新鲜度记录" />
        )}
      </Card>
    </Space>
  )
}
