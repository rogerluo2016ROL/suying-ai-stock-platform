import { useState, useEffect, useCallback } from 'react'
import { Card, Table, Tag, Typography, Space, Button, Badge, Tooltip, Modal, InputNumber, message } from 'antd'
import { SyncOutlined, ClockCircleOutlined, ExclamationCircleOutlined, InfoCircleOutlined, CloudDownloadOutlined, ThunderboltOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'

const { Title, Text } = Typography

interface DataSource {
  key: string; name: string; category: string; source: string
  update: string; note: string
  rows: number; min_date: string; max_date: string; status: string
}

interface SyncMapEntry { mode: string; days_default: number; desc: string }

const categoryColors: Record<string, string> = {
  '行情': 'blue', '资金': 'red', '特色': 'orange', '财务': 'purple', '基础': 'green', '舆情': 'cyan',
}

export default function DataUpdate() {
  const [sources, setSources] = useState<DataSource[]>([])
  const [syncMap, setSyncMap] = useState<Record<string, SyncMapEntry>>({})
  const [loading, setLoading] = useState(false)
  const [syncing, setSyncing] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState('')
  const [stats, setStats] = useState({ total_tables: 0, active_tables: 0, total_rows: 0 })
  const [syncModal, setSyncModal] = useState<{ open: boolean; key: string; name: string; mode: string; days: number }>({ open: false, key: '', name: '', mode: '', days: 30 })

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetch(`/api/v1/signal/data-status?_t=${Date.now()}`)
      if (r.ok) {
        const d = await r.json()
        setSources(d.sources || [])
        setSyncMap(d.sync_map || {})
        setLastRefresh(new Date().toLocaleTimeString('zh-CN', { hour12: false }))
        setStats({ total_tables: d.total_tables, active_tables: d.active_tables, total_rows: d.total_rows })
      }
    } catch { /* */ }
    finally { setLoading(false) }
  }, [])

  const triggerSync = async (key: string, days: number) => {
    setSyncing(key)
    try {
      const r = await fetch(`/api/v1/signal/trigger-sync?table_key=${key}&days=${days}`, { method: 'POST' })
      const d = await r.json()
      if (d.status === 'ok') {
        message.success(`${d.desc}: ${d.output?.[d.output.length-1] || 'sync completed'}`)
      } else {
        message.error(d.message || 'sync failed')
      }
    } catch { message.error('触发同步失败') }
    finally { setSyncing(null); fetchData() }
  }

  const openSyncModal = (key: string, name: string) => {
    const sm = syncMap[key]
    setSyncModal({ open: true, key, name, mode: sm?.mode || '', days: sm?.days_default || 30 })
  }

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
    {
      title: '同步', key: 'sync', width: 60, fixed: 'right',
      render: (_: unknown, record: DataSource) => {
        const hasSync = record.key in syncMap
        return hasSync ? (
          <Tooltip title={`同步 ${record.name}`}>
            <Button
              size="small" type="link" icon={<CloudDownloadOutlined />}
              loading={syncing === record.key}
              onClick={() => openSyncModal(record.key, record.name)}
              style={{ padding: 0 }}
            />
          </Tooltip>
        ) : (
          <Text type="secondary" style={{ fontSize: 10 }}>—</Text>
        )
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
          <Button size="small" icon={<ThunderboltOutlined />} onClick={() => {
            const syncable = sources.filter(s => s.key in syncMap)
            if (syncable.length === 0) { message.info('无可同步表'); return }
            syncable.forEach((s, i) => setTimeout(() => triggerSync(s.key, syncMap[s.key].days_default || 30), i * 2000))
            message.info(`开始同步 ${syncable.length} 张表...`)
          }}>一键同步全部</Button>
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
        <InfoCircleOutlined /> 数据来源: 各 PG 表实时统计, 端点 GET /api/v1/signal/data-status · 部分表无日期字段显示 "—" · 有 <CloudDownloadOutlined /> 图标的支持手动触发同步
      </Text>

      {/* Sync Modal */}
      <Modal
        title={<Space><CloudDownloadOutlined />同步: {syncModal.name}</Space>}
        open={syncModal.open}
        onCancel={() => setSyncModal(prev => ({ ...prev, open: false }))}
        onOk={() => { triggerSync(syncModal.key, syncModal.days); setSyncModal(prev => ({ ...prev, open: false })) }}
        okText="开始同步"
        okButtonProps={{ loading: syncing === syncModal.key }}
      >
        <div style={{ marginBottom: 16 }}>
          <Text type="secondary">同步模式: {syncModal.mode || '—'} · 从 Tushare 拉取数据并写入本地数据库</Text>
        </div>
        <Space direction="vertical" size="small" style={{ width: '100%' }}>
          <Text strong>同步天数 (从今天往前推):</Text>
          <InputNumber
            min={1} max={3650} value={syncModal.days}
            onChange={v => setSyncModal(prev => ({ ...prev, days: v || 30 }))}
            addonAfter="天"
            style={{ width: '100%' }}
          />
          <Text type="secondary" style={{ fontSize: 11 }}>
            日K线建议 30 天 · 周K线建议 365 天 · 月K线建议 730 天 · 集合竞价仅当天有效
          </Text>
        </Space>
      </Modal>
    </div>
  )
}
