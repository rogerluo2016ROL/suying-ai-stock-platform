import { useEffect, useMemo, useState } from 'react'
import { Button, Col, Empty, message, Row, Select, Space, Statistic, Table, Tag, Typography } from 'antd'
import type { TableColumnsType } from 'antd'
import { CheckCircleOutlined, CloseCircleOutlined, FileSearchOutlined, ReloadOutlined, WarningOutlined } from '@ant-design/icons'
import {
  screenerApi,
  type SupplyChainMappingQuality,
  type SupplyChainMappingReviewItem,
  type SupplyChainMappingReviewStatus,
} from '../../api/client'

const { Text, Title } = Typography

const CHAIN_NAMES: Record<string, string> = {
  advanced_manufacturing: '高端制造',
  ai_compute: 'AI算力',
  consumer_upgrade: '消费升级',
  cyclical_resources: '周期资源',
  defense: '国防军工',
  innovative_drug: '创新药',
  new_energy: '新能源',
  new_energy_vehicle: '新能源车',
  robotics: '机器人',
  semiconductor: '半导体',
}

function formatCount(value?: number) {
  return Number(value || 0).toLocaleString('zh-CN')
}

function statusColor(status?: string) {
  if (status === 'verified') return 'green'
  if (status === 'pending_review') return 'gold'
  if (status === 'weak_evidence') return 'orange'
  if (status === 'rejected') return 'red'
  return 'default'
}

function statusText(status?: string) {
  if (status === 'verified') return '已确认'
  if (status === 'pending_review') return '待复核'
  if (status === 'weak_evidence') return '弱证据'
  if (status === 'rejected') return '已驳回'
  return status || '待复核'
}

function sourceText(source?: string) {
  if (source === 'main_business') return '主营业务'
  if (source === 'introduction') return '公司简介'
  if (source === 'research_report') return '研报标题'
  if (source === 'industry') return '行业归属'
  return source || '未标注'
}

function nodeLabel(chainId?: string, nodeName?: string) {
  const chain = CHAIN_NAMES[chainId || ''] || chainId || '产业链'
  return `${chain}/${nodeName || '节点'}`
}

export default function SupplyChainMappingReviewPanel() {
  const [quality, setQuality] = useState<SupplyChainMappingQuality | null>(null)
  const [queue, setQueue] = useState<SupplyChainMappingReviewItem[]>([])
  const [queueTotal, setQueueTotal] = useState(0)
  const [status, setStatus] = useState<SupplyChainMappingReviewStatus>('reviewable')
  const [selectedNodeId, setSelectedNodeId] = useState('')
  const [qualityLoading, setQualityLoading] = useState(false)
  const [queueLoading, setQueueLoading] = useState(false)
  const [actingKey, setActingKey] = useState('')

  const queueParams = useMemo(() => ({
    status,
    nodeId: selectedNodeId || undefined,
    limit: 20,
    offset: 0,
  }), [selectedNodeId, status])

  const loadQuality = async () => {
    setQualityLoading(true)
    try {
      const resp = await screenerApi.getSupplyChainMappingQuality()
      setQuality(resp.data)
    } catch (err) {
      console.error('mapping quality load failed:', err)
      message.error('映射质量报告加载失败')
    } finally {
      setQualityLoading(false)
    }
  }

  const loadQueue = async () => {
    setQueueLoading(true)
    try {
      const resp = await screenerApi.getSupplyChainMappingReviewQueue(queueParams)
      setQueue(resp.data.items || [])
      setQueueTotal(resp.data.total || 0)
    } catch (err) {
      console.error('mapping review queue load failed:', err)
      message.error('复核队列加载失败')
    } finally {
      setQueueLoading(false)
    }
  }

  useEffect(() => {
    loadQuality()
  }, [])

  useEffect(() => {
    loadQueue()
  }, [queueParams])

  const applyDecision = async (
    row: SupplyChainMappingReviewItem,
    decision: 'verified' | 'rejected' | 'needs_more_evidence',
  ) => {
    const key = `${row.code}_${row.node_id}_${decision}`
    setActingKey(key)
    try {
      const note = decision === 'verified'
        ? '前端复核确认'
        : decision === 'rejected'
          ? '前端复核驳回'
          : '前端复核要求补充证据'
      await screenerApi.reviewSupplyChainMapping(row.code, row.node_id, {
        decision,
        reviewer: 'frontend',
        note,
      })
      message.success('复核结果已写回')
      await Promise.all([loadQuality(), loadQueue()])
    } catch (err) {
      console.error('mapping review decision failed:', err)
      message.error('复核写回失败')
    } finally {
      setActingKey('')
    }
  }

  const hotspotColumns: TableColumnsType<NonNullable<SupplyChainMappingQuality['hotspot_nodes']>[number]> = [
    {
      title: '热点节点',
      width: 180,
      render: (_: unknown, row: NonNullable<SupplyChainMappingQuality['hotspot_nodes']>[number]) => (
        <Space direction="vertical" size={2}>
          <Text strong>{nodeLabel(row.chain_id, row.node_name)}</Text>
          <Text type="secondary">{row.node_id}</Text>
        </Space>
      ),
    },
    { title: '压力', dataIndex: 'review_pressure', width: 76, render: (value: number) => <Tag color="red">{formatCount(value)}</Tag> },
    { title: '待审', dataIndex: 'pending_review', width: 76, render: (value: number) => formatCount(value) },
    { title: '弱证', dataIndex: 'weak_evidence', width: 76, render: (value: number) => formatCount(value) },
    {
      title: '操作',
      width: 78,
      render: (_: unknown, row: NonNullable<SupplyChainMappingQuality['hotspot_nodes']>[number]) => (
        <Button size="small" icon={<FileSearchOutlined />} onClick={() => setSelectedNodeId(row.node_id)}>
          查看
        </Button>
      ),
    },
  ]

  const queueColumns: TableColumnsType<SupplyChainMappingReviewItem> = [
    {
      title: '公司',
      width: 150,
      fixed: 'left',
      render: (_: unknown, row: SupplyChainMappingReviewItem) => (
        <Space direction="vertical" size={2}>
          <Text strong>{row.name || row.code}</Text>
          <Text type="secondary">{row.code}</Text>
        </Space>
      ),
    },
    {
      title: '映射节点',
      width: 220,
      render: (_: unknown, row: SupplyChainMappingReviewItem) => (
        <Space direction="vertical" size={2}>
          <Text>{nodeLabel(row.chain_id, row.node_name)}</Text>
          <Text type="secondary">{row.node_id}</Text>
        </Space>
      ),
    },
    {
      title: '状态/置信',
      width: 140,
      render: (_: unknown, row: SupplyChainMappingReviewItem) => (
        <Space direction="vertical" size={4}>
          <Tag color={statusColor(row.status)}>{statusText(row.status)}</Tag>
          <Text type="secondary">置信 {Number(row.confidence || 0).toFixed(2)}</Text>
        </Space>
      ),
    },
    { title: '来源', dataIndex: 'mapping_source', width: 110, render: (value: string) => sourceText(value) },
    {
      title: '证据',
      width: 280,
      render: (_: unknown, row: SupplyChainMappingReviewItem) => (
        <Space wrap={false} size={4}>
          {(row.evidence || []).slice(0, 3).map(item => <Tag key={item} color="blue">{item}</Tag>)}
          {!row.evidence?.length && <Text type="secondary">待补证据</Text>}
        </Space>
      ),
    },
    {
      title: '缺口',
      width: 360,
      render: (_: unknown, row: SupplyChainMappingReviewItem) => (
        <Space wrap={false} size={4}>
          {(row.evidence_gaps || []).slice(0, 3).map(item => <Tag key={item}>{item}</Tag>)}
        </Space>
      ),
    },
    {
      title: '优先级',
      dataIndex: 'review_priority',
      width: 90,
      sorter: (a: SupplyChainMappingReviewItem, b: SupplyChainMappingReviewItem) => Number(a.review_priority || 0) - Number(b.review_priority || 0),
      render: (value: number) => <Tag color="purple">{Number(value || 0).toFixed(0)}</Tag>,
    },
    {
      title: '复核',
      width: 236,
      fixed: 'right',
      render: (_: unknown, row: SupplyChainMappingReviewItem) => (
        <Space size={6} wrap={false}>
          <Button
            size="small"
            type="primary"
            icon={<CheckCircleOutlined />}
            loading={actingKey === `${row.code}_${row.node_id}_verified`}
            onClick={() => applyDecision(row, 'verified')}
          >
            确认
          </Button>
          <Button
            size="small"
            icon={<WarningOutlined />}
            loading={actingKey === `${row.code}_${row.node_id}_needs_more_evidence`}
            onClick={() => applyDecision(row, 'needs_more_evidence')}
          >
            补证据
          </Button>
          <Button
            size="small"
            danger
            icon={<CloseCircleOutlined />}
            loading={actingKey === `${row.code}_${row.node_id}_rejected`}
            onClick={() => applyDecision(row, 'rejected')}
          >
            驳回
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div style={{ border: '1px solid #f0f0f0', borderRadius: 8, background: '#fff', padding: 16 }}>
      <Space direction="vertical" size={14} style={{ width: '100%' }}>
        <Space align="center" style={{ justifyContent: 'space-between', width: '100%' }}>
          <Space wrap>
            <Title level={5} style={{ margin: 0 }}>映射复核</Title>
            <Tag color="gold">队列 {formatCount(queueTotal)}</Tag>
            {selectedNodeId && <Tag closable onClose={() => setSelectedNodeId('')}>节点筛选 {selectedNodeId}</Tag>}
          </Space>
          <Space wrap={false}>
            <Select
              value={status}
              style={{ width: 150 }}
              onChange={value => setStatus(value)}
              options={[
                { value: 'reviewable', label: '待复核+弱证据' },
                { value: 'pending_review', label: '仅待复核' },
                { value: 'weak_evidence', label: '仅弱证据' },
                { value: 'verified', label: '已确认' },
                { value: 'rejected', label: '已驳回' },
              ]}
            />
            <Button icon={<ReloadOutlined />} onClick={() => Promise.all([loadQuality(), loadQueue()])}>
              刷新
            </Button>
          </Space>
        </Space>

        <Row gutter={[12, 12]}>
          <Col xs={12} md={6}>
            <Statistic title="总映射" value={quality?.mapping_count || 0} loading={qualityLoading} />
          </Col>
          <Col xs={12} md={6}>
            <Statistic title="待复核" value={quality?.review_queue_count || 0} loading={qualityLoading} />
          </Col>
          <Col xs={12} md={6}>
            <Statistic title="已确认" value={quality?.status_counts?.verified || 0} loading={qualityLoading} />
          </Col>
          <Col xs={12} md={6}>
            <Statistic title="弱证据" value={quality?.status_counts?.weak_evidence || 0} loading={qualityLoading} />
          </Col>
        </Row>

        <Row gutter={[12, 12]}>
          <Col xs={24} xl={9}>
            <Table
              rowKey="node_id"
              size="small"
              loading={qualityLoading}
              columns={hotspotColumns}
              dataSource={quality?.hotspot_nodes || []}
              pagination={{ pageSize: 6, showSizeChanger: false }}
              scroll={{ x: 520 }}
              locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无热点节点" /> }}
            />
          </Col>
          <Col xs={24} xl={15}>
            <div data-testid="mapping-review-table-wrap" style={{ whiteSpace: 'nowrap' }}>
              <Table
                rowKey={row => `${row.code}_${row.node_id}`}
                size="small"
                loading={queueLoading}
                columns={queueColumns}
                dataSource={queue}
                pagination={false}
                scroll={{ x: 1586 }}
                locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无复核项" /> }}
              />
            </div>
          </Col>
        </Row>
      </Space>
    </div>
  )
}
