import { useState, useEffect, useCallback } from 'react'
import { Card, Table, Tag, Typography, Space, Button, Badge, Tooltip } from 'antd'
import { SyncOutlined, ClockCircleOutlined, CheckCircleOutlined, ExclamationCircleOutlined, InfoCircleOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'

const { Title, Text } = Typography

interface DataSource {
  key: string; name: string; category: string; source: string
  update: string; note: string
  rows: number; min_date: string; max_date: string; status: string
}

const categoryColors: Record<string, string> = {
  '行情': 'blue', '资金': 'red', '特色': 'orange', '财务': 'purple', '基础': 'green', '舆情': 'cyan',
}

export default function DataUpdate() {
  const [sources, setSources] = useState<DataSource[]>([])
  const [loading, setLoading] = useState(false)
  const [lastRefresh, setLastRefresh] = useState('')
  const [stats, setStats] = useState({ total_tables: 0, active_tables: 0, total_rows: 0 })

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetch(`/api/v1/signal/data-status?_t=${Date.now()}`)
      if (r.ok) {
        const d = await r.json()
        setSources(d.sources || [])
        setLastRefresh(new Date().toLocaleTimeString('zh-CN', { hour12: false }))
        setStats({ total_tables: d.total_tables, active_tables: d.active_tables, total_rows: d.total_rows })
      }
    } catch { /* */ }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const formatRows = (n: number) => {
    if (n > 1e7) return (n / 1e7).toFixed(1) + '千万'
    if (n > 1e4) return (n / 1e4).toFixed(1) + '万'
    return n.toLocaleString()
  }

  const columns: ColumnsType<DataSource> = [
    {
      title: '数据表', dataIndex: 'name', width: 160, fixed: 'left',
      render: (v: string, r: DataSource) => (
        <Space direction="vertical" size={0}>
          <Text strong style={{ fontSize: 13 }}>{v}</Text>
          <Text type="secondary" style={{ fontSize: 10, fontFamily: 'monospace' }}>{r.key}</Text>
        </Space>
      ),
    },
    {
      title: '分类', dataIndex: 'category', width: 70,
      render: (v: string) => <Tag color={categoryColors[v] || 'default'} style={{ fontSize: 10 }}>{v}</Tag>,
    },
    {
      title: '数据来源', dataIndex: 'source', width: 170,
      render: (v: string, r: DataSource) => (
        <Tooltip title={r.note || '—'}>
          <Text style={{ fontSize: 12 }}>{v}</Text>
        </Tooltip>
      ),
    },
    {
      title: '更新频率', dataIndex: 'update', width: 130,
      render: (v: string) => <Text style={{ fontSize: 11 }}>{v}</Text>,
    },
    {
      title: '数据起始', dataIndex: 'min_date', width: 90,
      render: (v: string) => <Text style={{ fontSize: 11, fontFamily: 'monospace' }}>{v}</Text>,
    },
    {
      title: '最新数据', dataIndex: 'max_date', width: 140,
      render: (v: string) => {
        if (!v || v === '—') return <Text type="secondary">—</Text>
        // Highlight if data is older than 2 days
        const dateStr = v.slice(0, 10)
        const daysAgo = Math.floor((Date.now() - new Date(dateStr).getTime()) / 86400000)
        return (
          <Space size={4}>
            <Text style={{
              fontSize: 11, fontFamily: 'monospace',
              color: daysAgo > 2 ? '#ff4d4f' : daysAgo > 1 ? '#fa8c16' : '#52c41a',
            }}>
              {v.slice(0,16)}
            </Text>
            {daysAgo > 1 && (
              <Tooltip title={`数据延迟 ${daysAgo} 天`}>
                <ExclamationCircleOutlined style={{ color: '#fa8c16', fontSize: 10 }} />
              </Tooltip>
            )}
          </Space>
        )
      },
    },
    {
      title: '行数', dataIndex: 'rows', width: 80,
      sorter: (a: DataSource, b: DataSource) => a.rows - b.rows,
      defaultSortOrder: 'descend',
      render: (v: number) => <Text style={{ fontSize: 11 }}>{formatRows(v)}</Text>,
    },
    {
      title: '状态', dataIndex: 'status', width: 70,
      render: (v: string) => {
        if (v === 'active') return <Badge status="success" text={<Text style={{ fontSize: 10 }}>正常</Text>} />
        if (v === 'empty') return <Badge status="default" text={<Text style={{ fontSize: 10 }}>空</Text>} />
        return <Badge status="error" text={<Text style={{ fontSize: 10 }}>异常</Text>} />
      },
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>
            <ClockCircleOutlined style={{ marginRight: 8, color: '#1677ff' }} />
            数据更新状态
          </Title>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {stats.active_tables}/{stats.total_tables} 表正常 · 合计 {formatRows(stats.total_rows)} 条数据
          </Text>
        </div>
        <Space>
          {lastRefresh && <Text type="secondary" style={{ fontSize: 12 }}>最近刷新: {lastRefresh}</Text>}
          <Button size="small" icon={<SyncOutlined />} loading={loading} onClick={fetchData}>刷新</Button>
        </Space>
      </div>

      <Card style={{ borderRadius: 8, marginBottom: 12 }} size="small">
        <Table
          columns={columns}
          dataSource={sources}
          rowKey="key"
          size="small"
          loading={loading}
          scroll={{ x: 1000 }}
          pagination={{ pageSize: 50, showSizeChanger: false }}
          locale={{ emptyText: '数据加载中...' }}
        />
      </Card>

      <Text type="secondary" style={{ fontSize: 11 }}>
        <InfoCircleOutlined /> 数据来源: 各 PG 表实时统计, 端点 GET /api/v1/signal/data-status · 部分表无日期字段显示 "—"
      </Text>
    </div>
  )
}
