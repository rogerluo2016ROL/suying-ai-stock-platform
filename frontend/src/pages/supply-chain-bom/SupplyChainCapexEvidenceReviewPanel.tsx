import { useEffect, useMemo, useState } from 'react'
import { Button, Empty, message, Select, Space, Table, Tag, Typography } from 'antd'
import { CheckCircleOutlined, CloseCircleOutlined, ReloadOutlined } from '@ant-design/icons'
import {
  screenerApi,
  type CapexEvidenceReviewItem,
  type SupplyChainCapexEvidenceReviewQueueParams,
} from '../../api/client'
import { formatNumber } from './formatters'

const { Text, Title } = Typography

function reviewStatusColor(status?: string) {
  if (status === 'approved') return 'green'
  if (status === 'rejected') return 'red'
  return 'gold'
}

function reviewStatusText(status?: string) {
  if (status === 'approved') return '已批准'
  if (status === 'rejected') return '已驳回'
  return '待审核'
}

export default function SupplyChainCapexEvidenceReviewPanel() {
  const [queue, setQueue] = useState<CapexEvidenceReviewItem[]>([])
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(false)
  const [actingKey, setActingKey] = useState('')
  const [chainId, setChainId] = useState('ai_compute')
  const [reviewStatus, setReviewStatus] = useState<SupplyChainCapexEvidenceReviewQueueParams['reviewStatus']>('pending_review')

  const loadQueue = async () => {
    setLoading(true)
    try {
      const resp = await screenerApi.getSupplyChainCapexEvidenceReviewQueue({
        limit: 80,
        chainId: chainId || undefined,
        reviewStatus,
      })
      setQueue(resp.data.queue || [])
      setCounts(resp.data.counts || {})
    } catch (err) {
      console.error('capex evidence review queue load failed:', err)
      message.error('CAPEX 证据审核队列加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadQueue()
  }, [chainId, reviewStatus])

  const reviewEvidence = async (row: CapexEvidenceReviewItem, status: 'approved' | 'rejected') => {
    const key = `${row.capex_evidence_id}_${status}`
    setActingKey(key)
    try {
      await screenerApi.reviewSupplyChainCapexEvidence(row.capex_evidence_id, {
        review_status: status,
        reviewer: 'frontend',
        note: status === 'approved' ? '前端审核批准' : '前端审核驳回',
        confidence: row.confidence,
      })
      message.success(status === 'approved' ? 'CAPEX 证据已批准' : 'CAPEX 证据已驳回')
      await loadQueue()
    } catch (err) {
      console.error('capex evidence review failed:', err)
      message.error('审核写回失败')
    } finally {
      setActingKey('')
    }
  }

  const chainOptions = useMemo(() => [
    { label: 'AI算力', value: 'ai_compute' },
    { label: '全部产业链', value: '' },
  ], [])

  const columns: any[] = [
    {
      title: '公司/映射',
      width: 190,
      fixed: 'left',
      render: (_: unknown, row: CapexEvidenceReviewItem) => (
        <Space direction="vertical" size={2}>
          <Text strong>{row.company_name || row.code}</Text>
          <Text type="secondary">{row.code} · {row.tag_name || row.mapping_id}</Text>
          <Tag color={reviewStatusColor(row.review_status)}>{reviewStatusText(row.review_status)}</Tag>
        </Space>
      ),
    },
    {
      title: '投入方向',
      width: 240,
      render: (_: unknown, row: CapexEvidenceReviewItem) => (
        <Space direction="vertical" size={4}>
          <Space size={4} wrap>
            {(row.capex_direction || []).slice(0, 6).map(item => <Tag key={item} color={row.direction_is_ai_related ? 'geekblue' : 'default'}>{item}</Tag>)}
          </Space>
          <Text type="secondary">{row.mapped_layer_id} / {(row.mapped_segments || []).join('、')}</Text>
        </Space>
      ),
    },
    {
      title: '金额/口径',
      width: 150,
      render: (_: unknown, row: CapexEvidenceReviewItem) => (
        <Space direction="vertical" size={2}>
          <Text>{row.capex_amount == null ? '未披露金额' : `${formatNumber(row.capex_amount, 2)} ${row.capex_amount_unit || row.currency || ''}`}</Text>
          <Text type="secondary">{row.amount_is_total_capex ? '总CAPEX' : row.amount_is_segment_capex ? '分部CAPEX' : '方向证据'}</Text>
        </Space>
      ),
    },
    {
      title: '来源',
      width: 210,
      render: (_: unknown, row: CapexEvidenceReviewItem) => (
        <Space direction="vertical" size={2}>
          <Text>{row.source_name || row.source_type}</Text>
          <Space size={4} wrap>
            <Tag>{row.source_level || 'unknown'}</Tag>
            <Tag>{row.evidence_level || 'directional'}</Tag>
            <Tag>置信 {formatNumber(Number(row.confidence || 0) * 100, 0)}%</Tag>
          </Space>
        </Space>
      ),
    },
    {
      title: '原文',
      width: 460,
      render: (_: unknown, row: CapexEvidenceReviewItem) => (
        <Text style={{ whiteSpace: 'normal' }}>{row.quote || '无原文'}</Text>
      ),
    },
    {
      title: '审核',
      width: 180,
      fixed: 'right',
      render: (_: unknown, row: CapexEvidenceReviewItem) => (
        <Space size={6}>
          <Button
            size="small"
            type="primary"
            icon={<CheckCircleOutlined />}
            loading={actingKey === `${row.capex_evidence_id}_approved`}
            onClick={() => reviewEvidence(row, 'approved')}
          >
            批准
          </Button>
          <Button
            size="small"
            danger
            icon={<CloseCircleOutlined />}
            loading={actingKey === `${row.capex_evidence_id}_rejected`}
            onClick={() => reviewEvidence(row, 'rejected')}
          >
            驳回
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <Space direction="vertical" size={14} style={{ width: '100%' }}>
      <Space align="center" style={{ justifyContent: 'space-between', width: '100%' }}>
        <Space direction="vertical" size={4}>
          <Title level={4} style={{ margin: 0 }}>CAPEX 证据审核</Title>
          <Text type="secondary">只批准有原文、方向和映射层级可信的记录；批准后才进入个股 CAPEX 评分。</Text>
        </Space>
        <Space wrap>
          <Select style={{ width: 150 }} value={chainId} options={chainOptions} onChange={setChainId} />
          <Select
            style={{ width: 140 }}
            value={reviewStatus}
            onChange={setReviewStatus}
            options={[
              { value: 'pending_review', label: '待审核' },
              { value: 'approved', label: '已批准' },
              { value: 'rejected', label: '已驳回' },
            ]}
          />
          <Tag color="gold">待审 {counts.pending_review || 0}</Tag>
          <Tag color="green">已批 {counts.approved || 0}</Tag>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={loadQueue}>刷新</Button>
        </Space>
      </Space>

      <Table
        rowKey="capex_evidence_id"
        size="small"
        loading={loading}
        columns={columns}
        dataSource={queue}
        pagination={{ pageSize: 20, showSizeChanger: false }}
        scroll={{ x: 1430 }}
        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无 CAPEX 审核记录" /> }}
      />
    </Space>
  )
}
