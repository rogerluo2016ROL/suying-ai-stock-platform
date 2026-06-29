import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  Button, Card, Col, Input, Row, Space, Table, Tag, Typography, message,
} from 'antd'
import {
  ArrowLeftOutlined, DeploymentUnitOutlined, ReloadOutlined, SafetyCertificateOutlined, SearchOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'

import { tradeApi } from '../api/client'
import type { DecisionContextQuery, DecisionContextRecord } from '../api/types'

const { Title, Text, Paragraph } = Typography

type DecisionContextFilters = Pick<DecisionContextQuery, 'decision_context_id' | 'code' | 'plan_id' | 'candidate_id'>

function getUrlFilters(search: string): Partial<DecisionContextFilters> {
  const params = new URLSearchParams(search)
  const filters: Partial<DecisionContextFilters> = {}
  ;(['decision_context_id', 'code', 'plan_id', 'candidate_id'] as const).forEach((key) => {
    const value = params.get(key)
    if (value) filters[key] = value
  })
  return filters
}

function compactPayload(payload: Record<string, unknown>): string {
  const entries = Object.entries(payload || {}).slice(0, 6)
  if (!entries.length) return '暂无上下文载荷'
  return entries.map(([key, value]) => `${key}: ${String(value)}`).join(' / ')
}

export default function DecisionContexts() {
  const navigate = useNavigate()
  const location = useLocation()
  const urlFilters = useMemo(() => getUrlFilters(location.search), [location.search])
  const [decisionContextId, setDecisionContextId] = useState(urlFilters.decision_context_id || '')
  const [code, setCode] = useState(urlFilters.code || '')
  const [planId, setPlanId] = useState(urlFilters.plan_id || '')
  const [candidateId, setCandidateId] = useState(urlFilters.candidate_id || '')
  const [data, setData] = useState<DecisionContextRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  const fetchContexts = useCallback(async (
    p = page,
    ps = pageSize,
    filters?: Partial<DecisionContextFilters>,
  ) => {
    setLoading(true)
    try {
      const activeFilters = filters || {
        decision_context_id: decisionContextId,
        code,
        plan_id: planId,
        candidate_id: candidateId,
      }
      const params: DecisionContextQuery = { page: p, page_size: ps }
      ;(['decision_context_id', 'code', 'plan_id', 'candidate_id'] as const).forEach((key) => {
        const value = activeFilters[key]
        if (value?.trim()) params[key] = value.trim()
      })

      const response = await tradeApi.getDecisionContexts(params)
      setData(response.data.records || [])
      setTotal(response.data.total || 0)
    } catch {
      message.error('获取决策上下文失败')
      setData([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [candidateId, code, decisionContextId, page, pageSize, planId])

  useEffect(() => {
    fetchContexts(1, pageSize)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleSearch = () => {
    setPage(1)
    fetchContexts(1, pageSize)
  }

  const handleReset = () => {
    const cleared: Partial<DecisionContextFilters> = {
      decision_context_id: '',
      code: '',
      plan_id: '',
      candidate_id: '',
    }
    setDecisionContextId('')
    setCode('')
    setPlanId('')
    setCandidateId('')
    setPage(1)
    fetchContexts(1, pageSize, cleared)
  }

  const columns = [
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 150,
      render: (value: string) => value ? dayjs(value).format('MM-DD HH:mm:ss') : '---',
    },
    {
      title: '上下文ID',
      dataIndex: 'decision_context_id',
      width: 150,
      render: (value: string) => <Text code>{value}</Text>,
    },
    {
      title: '来源',
      dataIndex: 'source_type',
      width: 90,
      render: (value: string) => <Tag color={value === 'order' ? 'blue' : 'default'}>{value}</Tag>,
    },
    {
      title: '股票',
      dataIndex: 'symbol',
      width: 90,
      render: (value: string) => value || '---',
    },
    {
      title: '链路',
      width: 220,
      render: (_: unknown, record: DecisionContextRecord) => (
        <Space direction="vertical" size={2}>
          <Space size={4} wrap>
            {record.plan_id && <Tag color="blue" style={{ marginInlineEnd: 0 }}>{record.plan_id}</Tag>}
            {record.candidate_id && <Tag style={{ marginInlineEnd: 0 }}>{record.candidate_id}</Tag>}
          </Space>
          <Text type="secondary" style={{ fontSize: 12 }}>{record.account_id || '默认账户'}</Text>
        </Space>
      ),
    },
    {
      title: '意图',
      dataIndex: 'intent',
      width: 120,
      render: (value: string) => value || '---',
    },
    {
      title: '载荷摘要',
      width: 320,
      render: (_: unknown, record: DecisionContextRecord) => (
        <Paragraph ellipsis={{ rows: 2 }} style={{ margin: 0 }}>
          {compactPayload(record.payload)}
        </Paragraph>
      ),
    },
    {
      title: '操作',
      width: 120,
      render: (_: unknown, record: DecisionContextRecord) => (
        <Button
          type="link"
          size="small"
          icon={<SafetyCertificateOutlined />}
          aria-label="关联风控"
          onClick={() => {
            const params = new URLSearchParams({ decision_context_id: record.decision_context_id })
            if (record.symbol) params.set('code', record.symbol)
            if (record.plan_id) params.set('plan_id', record.plan_id)
            if (record.candidate_id) params.set('candidate_id', record.candidate_id)
            navigate(`/trade/risk-verdicts?${params.toString()}`)
          }}
        >
          关联风控
        </Button>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Space>
          <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate('/trade')}>
            返回交易中心
          </Button>
          <Title level={4} style={{ margin: 0 }}>
            <DeploymentUnitOutlined style={{ marginRight: 8 }} />
            决策上下文
          </Title>
        </Space>
        <Button icon={<SafetyCertificateOutlined />} onClick={() => navigate('/trade/risk-verdicts')}>
          风控闸门
        </Button>
      </div>

      <Card size="small" style={{ marginBottom: 16, borderRadius: 8 }}>
        <Row gutter={[16, 12]} align="middle">
          <Col xs={24} sm={12} md={6}>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>上下文ID</Text>
            <Input value={decisionContextId} onChange={event => setDecisionContextId(event.target.value)} placeholder="CTX-..." allowClear size="small" />
          </Col>
          <Col xs={24} sm={12} md={5}>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>股票代码</Text>
            <Input value={code} onChange={event => setCode(event.target.value)} placeholder="搜索代码" allowClear size="small" />
          </Col>
          <Col xs={24} sm={12} md={5}>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>方案ID</Text>
            <Input value={planId} onChange={event => setPlanId(event.target.value)} placeholder="PLAN-..." allowClear size="small" />
          </Col>
          <Col xs={24} sm={12} md={5}>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>候选ID</Text>
            <Input value={candidateId} onChange={event => setCandidateId(event.target.value)} placeholder="CAND-..." allowClear size="small" />
          </Col>
          <Col xs={24} sm={12} md={3}>
            <Space style={{ marginTop: 20 }}>
              <Button type="primary" size="small" icon={<SearchOutlined />} onClick={handleSearch}>
                查询
              </Button>
              <Button size="small" icon={<ReloadOutlined />} onClick={handleReset}>
                重置
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>

      <Card style={{ borderRadius: 8 }}>
        <Table
          dataSource={data}
          columns={columns}
          rowKey={(record) => String(record.id ?? record.decision_context_id)}
          size="small"
          loading={loading}
          expandable={{
            expandedRowRender: (record) => (
              <pre style={{
                margin: 0,
                padding: 12,
                background: '#f6f8fb',
                borderRadius: 6,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}>
                {JSON.stringify(record.payload || {}, null, 2)}
              </pre>
            ),
          }}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            pageSizeOptions: ['10', '20', '50', '100'],
            showTotal: (count) => `共 ${count} 条上下文`,
          }}
          onChange={(pagination) => {
            const nextPage = pagination.current || 1
            const nextPageSize = pagination.pageSize || 20
            setPage(nextPage)
            setPageSize(nextPageSize)
            fetchContexts(nextPage, nextPageSize)
          }}
          locale={{
            emptyText: (
              <div style={{ padding: 24 }}>
                <Text type="secondary">暂无决策上下文记录</Text>
              </div>
            ),
          }}
        />
      </Card>
    </div>
  )
}
