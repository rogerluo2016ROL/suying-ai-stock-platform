import { useState, useEffect, useCallback } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Select,
  Input, DatePicker, Row, Col, message,
} from 'antd'
import {
  ArrowLeftOutlined, DownloadOutlined, SearchOutlined,
  ReloadOutlined, AuditOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { tradeApi } from '../api/domains/trade/api'
import type { AuditLogRecord } from '../api/types'
import dayjs from 'dayjs'

const { Title, Text } = Typography
const { RangePicker } = DatePicker

interface AuditLogQuery {
  page?: number
  page_size?: number
  start_date?: string
  end_date?: string
  action_type?: string
  stock_code?: string
  operator?: string
}

const ACTION_TYPES = [
  { value: 'ORDER_PLACED', label: '买入下单' },
  { value: 'ORDER_CANCELLED', label: '撤单' },
  { value: 'ORDER_FILLED', label: '成交' },
  { value: 'ORDER_REJECTED', label: '风控拦截' },
  { value: 'LARGE_TRADE_CONFIRMED', label: '大额确认' },
  { value: 'CIRCUIT_BREAKER', label: '熔断触发' },
  { value: 'BROKER_CONNECT', label: '券商连接' },
  { value: 'BROKER_DISCONNECT', label: '券商断开' },
  { value: 'MODE_SWITCH', label: '模式切换' },
  { value: 'STRATEGY_OPERATION', label: '策略操作' },
]

const actionColorMap: Record<string, string> = {
  ORDER_PLACED: 'blue',
  ORDER_CANCELLED: 'default',
  ORDER_FILLED: 'green',
  ORDER_REJECTED: 'red',
  LARGE_TRADE_CONFIRMED: 'orange',
  CIRCUIT_BREAKER: 'red',
  BROKER_CONNECT: 'green',
  BROKER_DISCONNECT: 'red',
  MODE_SWITCH: 'purple',
  STRATEGY_OPERATION: 'cyan',
}

export default function AuditLog() {
  const navigate = useNavigate()

  // ── Filter state ──
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null)
  const [actionType, setActionType] = useState<string | undefined>(undefined)
  const [stockCode, setStockCode] = useState('')
  const [operator, setOperator] = useState('')

  // ── Table state ──
  const [data, setData] = useState<AuditLogRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  // ── Fetch audit logs ──
  // P1-08: accept an optional filter override so callers (handleReset) can fetch
  // with the POST-reset values without waiting on async setState (the old code
  // used setTimeout(...,0) which raced under React 18 batching).
  const fetchLogs = useCallback(async (
    p?: number,
    ps?: number,
    overrideFilters?: { dateRange?: [dayjs.Dayjs, dayjs.Dayjs] | null; actionType?: string; stockCode?: string; operator?: string },
  ) => {
    setLoading(true)
    try {
      const currentPage = p ?? page
      const currentPageSize = ps ?? pageSize
      const fDateRange = overrideFilters ? overrideFilters.dateRange : dateRange
      const fActionType = overrideFilters ? overrideFilters.actionType : actionType
      const fStockCode = overrideFilters ? overrideFilters.stockCode : stockCode
      const fOperator = overrideFilters ? overrideFilters.operator : operator

      const params: AuditLogQuery = {
        page: currentPage,
        page_size: currentPageSize,
      }

      if (fDateRange && fDateRange[0] && fDateRange[1]) {
        params.start_date = fDateRange[0].format('YYYY-MM-DD')
        params.end_date = fDateRange[1].format('YYYY-MM-DD')
      }
      if (fActionType) params.action_type = fActionType
      if (fStockCode && fStockCode.trim()) params.stock_code = fStockCode.trim()
      if (fOperator && fOperator.trim()) params.operator = fOperator.trim()

      const r = await tradeApi.getAuditLogs(params)
      setData(r.data?.items || r.data?.logs || [])
      setTotal(r.data?.total || 0)
    } catch {
      message.error('获取审计日志失败')
      setData([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, dateRange, actionType, stockCode, operator])

  useEffect(() => {
    fetchLogs(1, pageSize)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Search / Reset ──
  const handleSearch = () => {
    setPage(1)
    fetchLogs(1, pageSize)
  }

  const handleReset = () => {
    const cleared = { dateRange: null, actionType: undefined, stockCode: '', operator: '' }
    setDateRange(null)
    setActionType(undefined)
    setStockCode('')
    setOperator('')
    setPage(1)
    // P1-08: fetch with the cleared filters directly (override) — no setTimeout.
    fetchLogs(1, pageSize, cleared)
  }

  // ── Export CSV ──
  const handleExport = async () => {
    try {
      const params: AuditLogQuery = {}
      if (dateRange && dateRange[0] && dateRange[1]) {
        params.start_date = dateRange[0].format('YYYY-MM-DD')
        params.end_date = dateRange[1].format('YYYY-MM-DD')
      }
      if (actionType) params.action_type = actionType
      if (stockCode.trim()) params.stock_code = stockCode.trim()
      if (operator.trim()) params.operator = operator.trim()

      const r = await tradeApi.exportAuditLogs(params)
      const blob = new Blob([r.data], { type: 'text/csv;charset=utf-8' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `审计日志_${dayjs().format('YYYY-MM-DD')}.csv`
      a.click()
      window.URL.revokeObjectURL(url)
      message.success('导出成功')
    } catch {
      message.error('导出失败')
    }
  }

  // ── Table change handler ──
  const handleTableChange = (pagination: { current?: number; pageSize?: number }) => {
    const p = pagination.current || 1
    const ps = pagination.pageSize || 20
    setPage(p)
    setPageSize(ps)
    fetchLogs(p, ps)
  }

  const columns = [
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 160,
      render: (v: string) => v ? dayjs(v).format('MM-DD HH:mm:ss') : '---',
    },
    {
      title: '操作类型',
      dataIndex: 'event_type',
      width: 120,
      render: (v: string) => {
        const label = ACTION_TYPES.find(t => t.value === v)?.label || v
        const color = actionColorMap[v] || 'default'
        return <Tag color={color}>{label}</Tag>
      },
    },
    {
      title: '股票代码',
      dataIndex: 'symbol',
      width: 100,
      render: (v: string) => v || '---',
    },
    {
      title: '方向',
      dataIndex: 'side',
      width: 60,
      render: (v: string) => v ? (
        <Tag color={v === 'BUY' ? 'red' : 'green'}>{v === 'BUY' ? '买' : '卖'}</Tag>
      ) : '---',
    },
    {
      title: '详情',
      dataIndex: 'detail',
      ellipsis: true,
      render: (v: AuditLogRecord['detail'], record: AuditLogRecord) => {
        if (v) return typeof v === 'string' ? v : JSON.stringify(v)
        // Build detail from record fields
        const parts: string[] = []
        if (record.quantity) parts.push(`${(record.quantity).toLocaleString()}股`)
        if (record.price) parts.push(`¥${Number(record.price).toFixed(2)}`)
        if (record.filled_qty) parts.push(`成交${record.filled_qty}股`)
        if (record.error_message) parts.push(record.error_message)
        return parts.join(' ') || '---'
      },
    },
    {
      title: '模式',
      dataIndex: 'mode',
      width: 80,
      render: (v: string) => (
        <Tag color={v === 'live' ? 'red' : 'blue'}>
          {v === 'live' ? '实盘' : '模拟'}
        </Tag>
      ),
    },
    {
      title: '操作人',
      dataIndex: 'operator',
      width: 100,
      render: (v: string) => v || '系统',
    },
    {
      title: 'IP 地址',
      dataIndex: 'ip_address',
      width: 130,
      responsive: ['lg' as const],
      render: (v: string) => v || '---',
    },
  ]

  return (
    <div>
      {/* ── Header ── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Space>
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate('/trade')}
          >
            返回交易中心
          </Button>
          <Title level={4} style={{ margin: 0 }}>
            <AuditOutlined style={{ marginRight: 8 }} />
            审计日志
          </Title>
        </Space>
        <Button icon={<DownloadOutlined />} onClick={handleExport}>
          导出 CSV
        </Button>
      </div>

      {/* ── Filters ── */}
      <Card size="small" style={{ marginBottom: 16, borderRadius: 8 }}>
        <Row gutter={[16, 12]} align="middle">
          <Col xs={24} sm={12} md={8} lg={6}>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>日期范围</Text>
            <RangePicker
              value={dateRange as any}
              onChange={(dates) => setDateRange(dates as unknown as [dayjs.Dayjs, dayjs.Dayjs])}
              style={{ width: '100%' }}
              size="small"
            />
          </Col>
          <Col xs={24} sm={12} md={8} lg={5}>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>操作类型</Text>
            <Select
              value={actionType}
              onChange={setActionType}
              placeholder="全部"
              allowClear
              style={{ width: '100%' }}
              size="small"
              options={ACTION_TYPES}
            />
          </Col>
          <Col xs={24} sm={12} md={8} lg={4}>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>股票代码</Text>
            <Input
              value={stockCode}
              onChange={e => setStockCode(e.target.value)}
              placeholder="搜索代码"
              allowClear
              size="small"
            />
          </Col>
          <Col xs={24} sm={12} md={8} lg={4}>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>操作人</Text>
            <Input
              value={operator}
              onChange={e => setOperator(e.target.value)}
              placeholder="操作人"
              allowClear
              size="small"
            />
          </Col>
          <Col xs={24} sm={12} md={4} lg={5}>
            <Space style={{ marginTop: 20 }}>
              <Button
                type="primary"
                size="small"
                icon={<SearchOutlined />}
                onClick={handleSearch}
              >
                查询
              </Button>
              <Button size="small" icon={<ReloadOutlined />} onClick={handleReset}>
                重置
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>

      {/* ── Table ── */}
      <Card style={{ borderRadius: 8 }}>
        <Table
          dataSource={data}
          columns={columns}
          rowKey={(record) => String(record.id ?? record.created_at ?? '')}
          size="small"
          loading={loading}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showQuickJumper: true,
            pageSizeOptions: ['10', '20', '50', '100'],
            showTotal: (t) => `共 ${t} 条记录`,
          }}
          onChange={handleTableChange}
          locale={{
            emptyText: (
              <div style={{ padding: 24 }}>
                <Text type="secondary">暂无审计日志记录</Text>
              </div>
            ),
          }}
        />
      </Card>
    </div>
  )
}
