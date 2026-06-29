import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  Button, Card, Col, Input, Row, Select, Space, Table, Tag, Typography, message,
} from 'antd'
import {
  ArrowLeftOutlined, AuditOutlined, ReloadOutlined, SearchOutlined, SafetyCertificateOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'

import { tradeApi } from '../api/client'
import type { RiskCheckItem, RiskVerdictQuery, RiskVerdictRecord } from '../api/types'
import { P0WorkflowNav } from '../components/layout'

const { Title, Text } = Typography

const resultOptions = [
  { value: 'pass', label: '通过' },
  { value: 'warn', label: '警告' },
  { value: 'reject', label: '拒绝' },
  { value: 'manual_review', label: '人工复核' },
]

const tradeModeOptions = [
  { value: 'paper', label: '模拟' },
  { value: 'live', label: '实盘' },
]

const resultColor: Record<string, string> = {
  pass: 'green',
  warn: 'gold',
  reject: 'red',
  manual_review: 'purple',
}

type RiskVerdictFilters = Pick<
  RiskVerdictQuery,
  'result' | 'trade_mode' | 'code' | 'decision_context_id' | 'order_id' | 'plan_id' | 'candidate_id'
>

function getUrlFilters(search: string): Partial<RiskVerdictFilters> {
  const params = new URLSearchParams(search)
  const filters: Partial<RiskVerdictFilters> = {}
  const result = params.get('result') as RiskVerdictQuery['result'] | null
  const tradeMode = params.get('trade_mode') as RiskVerdictQuery['trade_mode'] | null

  if (result) filters.result = result
  if (tradeMode) filters.trade_mode = tradeMode
  ;(['code', 'decision_context_id', 'order_id', 'plan_id', 'candidate_id'] as const).forEach((key) => {
    const value = params.get(key)
    if (value) filters[key] = value
  })

  return filters
}

function getChecks(record: RiskVerdictRecord): RiskCheckItem[] {
  const details = record.details as { risk_check?: { checks?: RiskCheckItem[] } }
  return details?.risk_check?.checks || []
}

export default function RiskVerdicts() {
  const navigate = useNavigate()
  const location = useLocation()
  const urlFilters = useMemo(() => getUrlFilters(location.search), [location.search])
  const [result, setResult] = useState<RiskVerdictQuery['result'] | undefined>(urlFilters.result)
  const [tradeMode, setTradeMode] = useState<RiskVerdictQuery['trade_mode'] | undefined>(urlFilters.trade_mode)
  const [code, setCode] = useState(urlFilters.code || '')
  const [data, setData] = useState<RiskVerdictRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  const fetchVerdicts = useCallback(async (
    p = page,
    ps = pageSize,
    filters?: Partial<RiskVerdictFilters>,
  ) => {
    setLoading(true)
    try {
      const activeResult = filters ? filters.result : result
      const activeTradeMode = filters ? filters.trade_mode : tradeMode
      const activeCode = (filters ? filters.code : code) || ''
      const params: RiskVerdictQuery = { page: p, page_size: ps }
      if (activeResult) params.result = activeResult
      if (activeTradeMode) params.trade_mode = activeTradeMode
      if (activeCode.trim()) params.code = activeCode.trim()
      const lineageFilters = filters || urlFilters
      ;(['decision_context_id', 'order_id', 'plan_id', 'candidate_id'] as const).forEach((key) => {
        const value = lineageFilters[key]
        if (value) params[key] = value
      })

      const response = await tradeApi.getRiskVerdicts(params)
      setData(response.data.records || [])
      setTotal(response.data.total || 0)
    } catch {
      message.error('获取风控判定失败')
      setData([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [code, page, pageSize, result, tradeMode, urlFilters])

  useEffect(() => {
    fetchVerdicts(1, pageSize)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleSearch = () => {
    setPage(1)
    fetchVerdicts(1, pageSize)
  }

  const handleReset = () => {
    const cleared: Partial<RiskVerdictFilters> = { result: undefined, trade_mode: undefined, code: '' }
    setResult(undefined)
    setTradeMode(undefined)
    setCode('')
    setPage(1)
    fetchVerdicts(1, pageSize, cleared)
  }

  const columns = [
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 150,
      render: (value: string) => value ? dayjs(value).format('MM-DD HH:mm:ss') : '---',
    },
    {
      title: '判定',
      dataIndex: 'result',
      width: 90,
      render: (value: string) => <Tag color={resultColor[value] || 'default'}>{value}</Tag>,
    },
    {
      title: '股票',
      dataIndex: 'symbol',
      width: 90,
      render: (value: string) => value || '---',
    },
    {
      title: '模式',
      dataIndex: 'trade_mode',
      width: 80,
      render: (value: string) => <Tag color={value === 'live' ? 'red' : 'blue'}>{value === 'live' ? '实盘' : '模拟'}</Tag>,
    },
    {
      title: '风控单号',
      dataIndex: 'verdict_id',
      width: 130,
      render: (value: string) => <Text code>{value}</Text>,
    },
    {
      title: '来源',
      width: 220,
      render: (_: unknown, record: RiskVerdictRecord) => (
        <Space direction="vertical" size={2}>
          <Space size={4} wrap>
            {record.plan_id && <Tag color="blue" style={{ marginInlineEnd: 0 }}>{record.plan_id}</Tag>}
            {record.candidate_id && <Tag style={{ marginInlineEnd: 0 }}>{record.candidate_id}</Tag>}
          </Space>
          {record.decision_context_id && <Text code style={{ fontSize: 11 }}>{record.decision_context_id}</Text>}
        </Space>
      ),
    },
    {
      title: '规则',
      width: 260,
      render: (_: unknown, record: RiskVerdictRecord) => (
        <Space direction="vertical" size={4}>
          {getChecks(record).slice(0, 3).map((check, index) => (
            <Space key={`${check.rule}-${index}`} size={6} wrap>
              <Tag color={resultColor[check.level] || 'default'} style={{ marginInlineEnd: 0 }}>{check.level}</Tag>
              <Text strong>{check.rule}</Text>
              {check.message && <Text type="secondary">{check.message}</Text>}
            </Space>
          ))}
          {getChecks(record).length === 0 && <Text type="secondary">暂无规则明细</Text>}
        </Space>
      ),
    },
    {
      title: '账户',
      dataIndex: 'account_id',
      width: 120,
      render: (value: string) => value || '---',
    },
    {
      title: '操作',
      width: 120,
      render: (_: unknown, record: RiskVerdictRecord) => (
        <Space>
          <Button
            type="link"
            size="small"
            disabled={!record.decision_context_id}
            onClick={() => {
              if (!record.decision_context_id) return
              const params = new URLSearchParams({ decision_context_id: record.decision_context_id })
              if (record.symbol) params.set('code', record.symbol)
              if (record.plan_id) params.set('plan_id', record.plan_id)
              if (record.candidate_id) params.set('candidate_id', record.candidate_id)
              navigate(`/trade/decision-contexts?${params.toString()}`)
            }}
          >
            决策上下文
          </Button>
        </Space>
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
            <SafetyCertificateOutlined style={{ marginRight: 8 }} />
            风控闸门
          </Title>
        </Space>
        <Button icon={<AuditOutlined />} onClick={() => navigate('/trade/audit-log')}>
          审计日志
        </Button>
      </div>

      <P0WorkflowNav currentStep="risk" />

      <Card size="small" style={{ marginBottom: 16, borderRadius: 8 }}>
        <Row gutter={[16, 12]} align="middle">
          <Col xs={24} sm={12} md={6}>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>判定结果</Text>
            <Select
              value={result}
              onChange={setResult}
              allowClear
              placeholder="全部"
              size="small"
              options={resultOptions}
              style={{ width: '100%' }}
            />
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>交易模式</Text>
            <Select
              value={tradeMode}
              onChange={setTradeMode}
              allowClear
              placeholder="全部"
              size="small"
              options={tradeModeOptions}
              style={{ width: '100%' }}
            />
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>股票代码</Text>
            <Input value={code} onChange={event => setCode(event.target.value)} placeholder="搜索代码" allowClear size="small" />
          </Col>
          <Col xs={24} sm={12} md={6}>
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
          rowKey={(record) => String(record.id ?? record.verdict_id)}
          size="small"
          loading={loading}
          expandable={{
            expandedRowRender: (record) => (
              <div style={{ padding: '4px 0 4px 40px' }}>
                <Text strong style={{ display: 'block', marginBottom: 8 }}>规则级详情</Text>
                <Space direction="vertical" size={6} style={{ width: '100%' }}>
                  {getChecks(record).map((check, index) => (
                    <Space key={`${check.rule}-${index}`} size={8} wrap>
                      <Tag color={resultColor[check.level] || 'default'} style={{ marginInlineEnd: 0 }}>{check.level}</Tag>
                      <Text strong>{check.rule}</Text>
                      {check.message && <Text type="secondary">{check.message}</Text>}
                    </Space>
                  ))}
                  {getChecks(record).length === 0 && <Text type="secondary">暂无规则明细</Text>}
                </Space>
              </div>
            ),
          }}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            pageSizeOptions: ['10', '20', '50', '100'],
            showTotal: (count) => `共 ${count} 条判定`,
          }}
          onChange={(pagination) => {
            const nextPage = pagination.current || 1
            const nextPageSize = pagination.pageSize || 20
            setPage(nextPage)
            setPageSize(nextPageSize)
            fetchVerdicts(nextPage, nextPageSize)
          }}
          locale={{
            emptyText: (
              <div style={{ padding: 24 }}>
                <Text type="secondary">暂无风控判定记录</Text>
              </div>
            ),
          }}
        />
      </Card>
    </div>
  )
}
