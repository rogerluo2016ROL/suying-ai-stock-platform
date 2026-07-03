import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Col, Empty, Progress, Row, Select, Space, Table, Tag, Typography } from 'antd'
import type { TableColumnsType } from 'antd'
import { EyeOutlined, ReloadOutlined } from '@ant-design/icons'
import { screenerApi, type SupplyChainCandidateRankingItem, type SupplyChainCandidateRankingResponse } from '../../api/client'
import type { CandidateCompany } from './types'
import { formatNumber } from './formatters'
import { lightTokens } from '../../styles/tokens'

const { Text, Title } = Typography

interface SupplyChainCandidateRankingPanelProps {
  onOpenCompany?: (company: CandidateCompany) => void
}

const signalColor: Record<string, string> = {
  重点候选: 'red',
  观察: 'orange',
  暂缓: 'default',
}

function toPercent(value?: number) {
  const n = Number(value)
  if (!Number.isFinite(n)) return 0
  return Math.max(0, Math.min(100, n <= 1 ? n * 100 : n))
}

function rowToCompany(row: SupplyChainCandidateRankingItem): CandidateCompany {
  return {
    code: row.code,
    name: row.name,
    industry: row.industry,
    rank: row.rank,
    chain: row.chain_id,
    layer: row.best_tag_name,
    node_id: row.node_id,
    node_name: row.best_tag_name,
    score: row.rank_score,
    rating: row.signal,
    trade_signal: row.signal,
    mapping_id: row.best_mapping_id,
    mapping_status: row.mapping_status,
    last_trade_date: row.latest_trade_date,
    last_price: row.latest_price,
    last_change_pct: row.change_1d_pct,
    candidate_source: 'supply-chain-candidate-ranking',
    pool_status: row.signal,
    commercialization_stage: row.commercialization_stage,
    dimension_scores: {
      growth: row.growth_score ?? 0,
      profit: row.profit_score ?? 0,
      moat: row.moat_score ?? 0,
      stage: row.stage_score ?? 0,
      evidence: row.evidence_score ?? 0,
      expectation_gap: row.expectation_gap_score ?? 0,
      l8_match_rate: toPercent(row.l8_match_rate),
      fresh_rate: toPercent(row.fresh_rate),
    },
    evidence_gaps: row.freshness_status && row.freshness_status !== 'fresh' ? [`证据新鲜度：${row.freshness_status}`] : [],
    selection_reason: `${row.chain_id} / ${row.best_tag_name}，三高 ${formatNumber(row.three_high_total, 1)}，L8证据 ${formatNumber(toPercent(row.l8_match_rate), 0)}%`,
  }
}

export default function SupplyChainCandidateRankingPanel({ onOpenCompany }: SupplyChainCandidateRankingPanelProps) {
  const [data, setData] = useState<SupplyChainCandidateRankingResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [chainId, setChainId] = useState<string>()
  const [signal, setSignal] = useState<string>()

  const loadRanking = () => {
    setLoading(true)
    setError('')
    screenerApi.getSupplyChainCandidateRanking({ topN: 120 })
      .then(resp => setData(resp.data))
      .catch(() => {
        setData(null)
        setError('候选总榜接口加载失败，请确认 screener-service 已更新并能访问真实数据库。')
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadRanking()
  }, [])

  const chainOptions = useMemo(() => {
    const ids = new Set<string>()
    data?.items.forEach(item => {
      if (item.chain_id) ids.add(item.chain_id)
    })
    return Array.from(ids).sort().map(id => ({ label: id, value: id }))
  }, [data])

  const signalOptions = useMemo(() => (
    Object.keys(data?.summary.signal_distribution || {}).map(item => ({ label: item, value: item }))
  ), [data])

  const rows = useMemo(() => {
    return (data?.items || []).filter(item => {
      if (chainId && item.chain_id !== chainId) return false
      if (signal && item.signal !== signal) return false
      return true
    })
  }, [chainId, data, signal])

  const openEvidence = (row: SupplyChainCandidateRankingItem) => {
    onOpenCompany?.(rowToCompany(row))
  }

  const columns: TableColumnsType<SupplyChainCandidateRankingItem> = [
    {
      title: '排名/公司',
      width: 190,
      fixed: 'left',
      render: (_, row) => (
        <Space direction="vertical" size={2}>
          <Space size={6}>
            <Tag color="blue">#{row.rank}</Tag>
            <Text strong>{row.name || row.code}</Text>
          </Space>
          <Text type="secondary">{row.code} {row.industry || ''}</Text>
        </Space>
      ),
    },
    {
      title: '产业链标签',
      width: 220,
      render: (_, row) => (
        <Space direction="vertical" size={2}>
          <Text>{row.best_tag_name}</Text>
          <Space size={4} wrap>
            <Tag>{row.chain_id}</Tag>
            <Tag color="cyan">{row.tag_count} 标签</Tag>
          </Space>
        </Space>
      ),
    },
    {
      title: '信号/总分',
      width: 140,
      render: (_, row) => (
        <Space direction="vertical" size={2}>
          <Tag color={signalColor[row.signal] || 'processing'}>{row.signal}</Tag>
          <Text strong>{formatNumber(row.rank_score, 2)}</Text>
        </Space>
      ),
    },
    {
      title: '三高',
      width: 170,
      render: (_, row) => (
        <Space direction="vertical" size={2}>
          <Text>总分 {formatNumber(row.three_high_total, 1)}</Text>
          <Text type="secondary">高成长 {formatNumber(row.growth_score, 0)} / 高盈利 {formatNumber(row.profit_score, 0)} / 高围墙 {formatNumber(row.moat_score, 0)}</Text>
        </Space>
      ),
    },
    {
      title: '阶段',
      width: 190,
      render: (_, row) => (
        <Space direction="vertical" size={2}>
          <Tag color="purple">{row.research_stage || '待确认研发阶段'}</Tag>
          <Tag color="green">{row.commercialization_stage || '待确认商用阶段'}</Tag>
        </Space>
      ),
    },
    {
      title: 'L8证据',
      width: 150,
      render: (_, row) => (
        <Space direction="vertical" size={2} style={{ width: '100%' }}>
          <Progress percent={toPercent(row.l8_match_rate)} size="small" />
          <Text type="secondary">{row.fact_count || 0} 条事实 / {row.freshness_status || 'unknown'}</Text>
        </Space>
      ),
    },
    {
      title: '预期差',
      width: 140,
      render: (_, row) => (
        <Space direction="vertical" size={2}>
          <Text>{formatNumber(row.expectation_gap_score, 1)}</Text>
          <Text type="secondary">{row.gap_type || '未分类'}</Text>
        </Space>
      ),
    },
    {
      title: '行情',
      width: 150,
      render: (_, row) => (
        <Space direction="vertical" size={2}>
          <Text>{formatNumber(row.latest_price, 2)}</Text>
          <Space size={4}>
            <Tag color={Number(row.change_1d_pct) >= 0 ? 'red' : 'green'}>{formatNumber(row.change_1d_pct, 2)}%</Tag>
            <Text type="secondary">20日 {formatNumber(row.change_20d_pct, 2)}%</Text>
          </Space>
        </Space>
      ),
    },
    {
      title: '操作',
      width: 120,
      fixed: 'right',
      render: (_, row) => (
        <Button icon={<EyeOutlined />} onClick={() => openEvidence(row)}>
          查看证据
        </Button>
      ),
    },
  ]

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Space align="center" style={{ justifyContent: 'space-between', width: '100%' }}>
        <Space direction="vertical" size={4}>
          <Title level={4} style={{ margin: 0 }}>候选总榜</Title>
          <Text type="secondary">后端真实落库数据排序：产业链标签、三高、研发/商用阶段、L8证据、预期差和行情共同打分。</Text>
        </Space>
        <Button icon={<ReloadOutlined />} loading={loading} onClick={loadRanking}>
          刷新
        </Button>
      </Space>

      {error && <Alert type="error" showIcon message={error} />}
      {data?.limitations?.length ? (
        <Alert type="warning" showIcon message="数据限制" description={data.limitations.join('；')} />
      ) : null}

      <Row gutter={[12, 12]}>
        <Col xs={12} md={6}><Card size="small"><Text type="secondary">映射行</Text><div style={{ fontSize: 24, fontWeight: 700 }}>{data?.summary.mapping_rows || 0}</div></Card></Col>
        <Col xs={12} md={6}><Card size="small"><Text type="secondary">公司-产业链</Text><div style={{ fontSize: 24, fontWeight: 700 }}>{data?.summary.company_chain_rows || 0}</div></Card></Col>
        <Col xs={12} md={6}><Card size="small"><Text type="secondary">产业链</Text><div style={{ fontSize: 24, fontWeight: 700 }}>{data?.summary.chain_count || 0}</div></Card></Col>
        <Col xs={12} md={6}><Card size="small"><Text type="secondary">重点候选</Text><div style={{ fontSize: 24, fontWeight: 700, color: lightTokens.up }}>{data?.summary.signal_distribution?.重点候选 || 0}</div></Card></Col>
      </Row>

      <Space wrap>
        <Select
          allowClear
          placeholder="按产业链筛选"
          style={{ width: 220 }}
          value={chainId}
          options={chainOptions}
          onChange={setChainId}
        />
        <Select
          allowClear
          placeholder="按信号筛选"
          style={{ width: 160 }}
          value={signal}
          options={signalOptions}
          onChange={setSignal}
        />
        <Tag color="blue">当前 {rows.length} 家</Tag>
        <Tag>{data?.source_status || 'loading'}</Tag>
      </Space>

      <Table
        rowKey={row => `${row.chain_id}-${row.code}-${row.best_mapping_id}`}
        loading={loading}
        size="small"
        columns={columns}
        dataSource={rows}
        pagination={{ pageSize: 20, showSizeChanger: false }}
        scroll={{ x: 1430 }}
        locale={{
          emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无候选排序数据" />,
        }}
      />
    </Space>
  )
}
