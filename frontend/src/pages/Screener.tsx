import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Select, Button, Table, Tag, Space, Typography, InputNumber, message, Row, Col } from 'antd'
import { PlayCircleOutlined, TrophyOutlined, FilterOutlined, FileTextOutlined, InfoCircleOutlined } from '@ant-design/icons'
import { screenerApi, strategyApi } from '../api/client'
import type { ScreenerPick, ScreenerMode, SectorResonance, ScreenerRunResponse, ScreenerModesResponse, StrategyPlan } from '../api/types'
import type { StrategyPick } from '../api/client'

const { Title, Text } = Typography

export default function Screener() {
  const navigate = useNavigate()
  const [modes, setModes] = useState<ScreenerMode[]>([])
  const [mode, setMode] = useState('leader_auction')
  const [topN, setTopN] = useState(20)
  const [loading, setLoading] = useState(false)
  const [picks, setPicks] = useState<ScreenerPick[]>([])
  const [marketEnv, setMarketEnv] = useState('')
  const [stats, setStats] = useState({ scored: 0, excluded: 0, elapsed: 0 })
  const [sectorResonance, setSectorResonance] = useState<SectorResonance[]>([])
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])
  const [sortBy, setSortBy] = useState<'score' | 'price'>('score')
  const [expandedRow, setExpandedRow] = useState<string | null>(null)

  const generatePlan = async () => {
    const selectedPicks = picks.filter((p) => selectedRowKeys.includes(p.code))
    if (selectedPicks.length === 0) { message.warning('请先勾选股票'); return }
    try {
      const r1 = await strategyApi.createPlan(
        `选股方案-${new Date().toLocaleDateString()}`, mode, selectedPicks.length)
      const plan = r1.data
      await strategyApi.addPicks(plan.plan.id, selectedPicks as unknown as StrategyPick[])
      message.success(`预方案已生成: ${plan.plan.id} (${selectedPicks.length}只)`)
      setSelectedRowKeys([])
    } catch { message.error('方案生成失败，请检查strategy-service是否启动') }
  }

  useEffect(() => {
    screenerApi.getModes().then(r => setModes((r.data as ScreenerModesResponse).modes || [])).catch(() => {})
  }, [])

  const runScreening = async () => {
    setLoading(true)
    try {
      const r = await screenerApi.run(mode, topN)
      const data = r.data as ScreenerRunResponse
      setPicks(data.picks || [])
      setSectorResonance(data.sector_resonance || [])
      setMarketEnv(data.market_env || '')
      setStats({
        scored: data.total_scored || data.picks?.length || 0,
        excluded: data.total_excluded || 0,
        elapsed: data.elapsed || 0,
      })
      message.success(`选股完成: ${data.total_scored || data.picks?.length || 0} 只 | ${(data.elapsed || 0).toFixed(0)}s`)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      message.error(err.response?.data?.detail || '选股失败')
    } finally { setLoading(false) }
  }

  // 活排序：Immutable copy + 实时响应 sortBy 选择器
  const sortedPicks = useMemo(() => {
    const copy = [...picks]
    if (sortBy === 'price') {
      copy.sort((a, b) => (Number(b.price) || 0) - (Number(a.price) || 0))
    } else {
      // default: by score descending
      copy.sort((a, b) => (Number(b.score) || 0) - (Number(a.score) || 0))
    }
    return copy
  }, [picks, sortBy])

  // 硬科技赛道颜色（使用设计token）
  const hardTechTagColor = (tier?: string): string => {
    if (tier === 'core') return 'red'      // var(--up) 核心层
    if (tier === 'strategic') return 'blue' // var(--accent) 战略层
    return 'default'                        // 供应层
  }

  // 四轴评分格式化
  const formatAxisScore = (label: string, value: number | undefined | null): string | null => {
    if (value === undefined || value === null) return null
    return `${label} ${Number(value).toFixed(1)}`
  }

  // 是否有四轴详情
  const hasFourAxisDetail = (record: ScreenerPick): boolean => (
    Boolean(record.entry_reason || record.factor_breakdown || record.hard_tech ||
      record.risk_flags?.length || record.power_flags?.length)
  )

  // 禁止换行样式
  const nowrapCell = () => ({ style: { whiteSpace: 'nowrap' as const } })

  // 表格列定义
  const columns = [
    { title: '#', width: 40, render: (_: unknown, __: unknown, i: number) => (
      <Text type="secondary" style={{ fontSize: 12 }}>{i + 1}</Text>
    ), onCell: nowrapCell },
    { title: '代码', dataIndex: 'code', width: 100, render: (v: string) => (
      <a onClick={() => navigate(`/diagnosis?code=${v}`)} style={{ cursor: 'pointer' }}>
        <Text code style={{ fontSize: 12, fontFamily: 'var(--font-mono)' }}>{v}</Text>
      </a>
    ), onCell: nowrapCell },
    { title: '名称', dataIndex: 'name', width: 130, render: (v: string, record: ScreenerPick) => (
      <div>
        <a onClick={() => navigate(`/diagnosis?code=${record.code}`)}
           style={{ cursor: 'pointer', color: 'var(--accent)' }}>
          {v || record.name}
        </a>
        {record.hard_tech?.track && (
          <div style={{ marginTop: 2, display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap' }}>
            <Tag color={hardTechTagColor(record.hard_tech?.tier)} style={{ marginInlineEnd: 0, fontSize: 11 }}>
              {record.hard_tech.track}
            </Tag>
            {record.hard_tech?.tier && (
              <Tag color="default" style={{ marginInlineEnd: 0, fontSize: 11 }}>
                {record.hard_tech.tier}
              </Tag>
            )}
            {hasFourAxisDetail(record) && (
              <Button
                type="link"
                size="small"
                aria-label="展开四轴解释"
                aria-pressed={expandedRow === record.code}
                style={{ height: 18, padding: 0, fontSize: 11 }}
                onClick={(e) => {
                  e.stopPropagation()
                  setExpandedRow(expandedRow === record.code ? null : record.code)
                }}
              >
                四轴
              </Button>
            )}
          </div>
        )}
      </div>
    ), onCell: nowrapCell },
    { title: '行业', dataIndex: 'industry', width: 95, ellipsis: true, onCell: nowrapCell },
    { title: '涨停', dataIndex: 'is_at_limit', width: 58, render: (v: boolean) => (
      v ? <Tag color="red" style={{ marginInlineEnd: 0, background: 'var(--up-bg)', borderColor: 'var(--up)' }}>是</Tag> : <Text type="secondary">否</Text>
    ), onCell: nowrapCell },
    { title: '价格', dataIndex: 'price', width: 70, render: (v: number) => (
      <span className="mono">{v?.toFixed(2)}</span>
    ), onCell: nowrapCell },
    { title: '评分', dataIndex: 'score', width: 65,
      sorter: true,
      sortIcon: () => null,
      render: (v: number) => (
      <Text strong className="mono" style={{
        color: v >= 16 ? 'var(--up)' : v >= 12 ? 'var(--warn)' : 'var(--accent)'
      }}>
        {v?.toFixed(1)}
      </Text>
    ), onCell: nowrapCell },
    { title: '等级', dataIndex: 'grade', width: 50, render: (v: string) => {
      const color = v === 'S' ? 'var(--up)' : v === 'A' ? 'var(--warn)' : v === 'B' ? 'var(--accent)' : 'var(--muted)'
      return <Tag style={{ fontWeight: 600, color, borderColor: color }}>{v}</Tag>
    }, onCell: nowrapCell },
    { title: '共振', dataIndex: 'resonance_score', width: 65, render: (v: number) => (
      v === undefined || v === null ? <Text type="secondary">--</Text> : <span className="mono">{Number(v).toFixed(1)}</span>
    ), onCell: nowrapCell },
    { title: '入场', dataIndex: 'entry_price', width: 70, render: (v: number | undefined) => v ? (
      <Text className="mono" style={{ color: 'var(--down)' }}>{Number(v).toFixed(2)}</Text>
    ) : <Text type="secondary">--</Text>, onCell: nowrapCell },
    { title: '止损', dataIndex: 'stop_loss', width: 70, render: (v: number | undefined) => v ? (
      <Text className="mono" style={{ color: 'var(--up)' }}>{Number(v).toFixed(2)}</Text>
    ) : <Text type="secondary">--</Text>, onCell: nowrapCell },
    { title: '目标', dataIndex: 'target_price', width: 70, render: (v: number | undefined) => v ? (
      <Text className="mono" style={{ color: 'var(--accent)' }}>{Number(v).toFixed(2)}</Text>
    ) : <Text type="secondary">--</Text>, onCell: nowrapCell },
  ]

  // 板块共振表格列
  const sectorColumns = [
    { title: '板块', dataIndex: 'sector', width: 110, ellipsis: true, onCell: nowrapCell },
    { title: '入选', dataIndex: 'pick_count', width: 58, render: (v: number) => <span className="mono">{v}</span>, onCell: nowrapCell },
    { title: '代表个股', dataIndex: 'representatives', width: 220, render: (v: string[]) => (
      <Text>{(v || []).join(' / ')}</Text>
    ), onCell: nowrapCell },
    { title: '均共振', dataIndex: 'avg_resonance_score', width: 75, render: (v: number) => <span className="mono">{Number(v || 0).toFixed(1)}</span>, onCell: nowrapCell },
    { title: '板块涨幅', dataIndex: 'avg_sector_change', width: 85, render: (v: number) => {
      const val = Number(v || 0)
      const color = val > 0 ? 'var(--up)' : val < 0 ? 'var(--down)' : 'var(--fg)'
      return <span className="mono" style={{ color }}>{val.toFixed(2)}%</span>
    }, onCell: nowrapCell },
    { title: '同板样本', dataIndex: 'max_peer_count', width: 80, render: (v: number) => <span className="mono">{v}</span>, onCell: nowrapCell },
  ]

  return (
    <div>
      {/* ── 页面标题 ── */}
      <div style={{ marginBottom: 24 }}>
        <h1 className="section-title" style={{ fontFamily: 'var(--font-display)' }}>
          智能选股
        </h1>
        <Text type="secondary" style={{ color: 'var(--muted)' }}>
          12套内置策略 · 全市场5000+标的 · 多因子智能排序
        </Text>
      </div>

      {/* ── 控制面板 ── */}
      <Card style={{ borderRadius: 'var(--radius)', marginBottom: 16, background: 'var(--surface)', borderColor: 'var(--border)' }}>
        <Row gutter={[16, 12]} align="middle">
          <Col>
            <Space>
              <FilterOutlined style={{ color: 'var(--muted)' }} />
              <Select
                value={mode}
                onChange={setMode}
                style={{ width: 220 }}
                aria-label="选择策略模式"
                options={modes.map((m) => ({
                  label: `${m.name} (${m.style || 'balanced'})`,
                  value: m.id
                }))}
              />
            </Space>
          </Col>
          <Col>
            <Space>
              <TrophyOutlined style={{ color: 'var(--muted)' }} />
              <InputNumber
                min={5}
                max={100}
                value={topN}
                onChange={v => setTopN(v || 20)}
                aria-label="选股数量"
                style={{ width: 80 }}
                className="mono"
              />
              <Text type="secondary" style={{ fontSize: 12, color: 'var(--muted)' }}>只</Text>
            </Space>
          </Col>
          <Col>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              loading={loading}
              onClick={runScreening}
              size="middle"
              aria-busy={loading}
              style={{ background: 'var(--accent)', borderColor: 'var(--accent)' }}
            >
              {loading ? '选股中...' : '开始选股'}
            </Button>
            {picks.length > 0 && (
              <Button
                icon={<FileTextOutlined />}
                onClick={generatePlan}
                disabled={selectedRowKeys.length === 0}
                aria-label={`生成预方案（已选 ${selectedRowKeys.length} 只）`}
              >
                生成预方案 ({selectedRowKeys.length})
              </Button>
            )}
          </Col>
          {marketEnv && (
            <Col>
              <Tag style={{ background: 'var(--accent-dim)', borderColor: 'var(--accent)', color: 'var(--accent)' }}>
                {marketEnv}
              </Tag>
            </Col>
          )}
          {stats.elapsed > 0 && (
            <>
              <Col>
                <Select
                  size="small"
                  value={sortBy}
                  onChange={(v) => setSortBy(v as 'score' | 'price')}
                  style={{ width: 130 }}
                  aria-label="排序方式"
                  options={[
                    { label: '按评分排序', value: 'score' },
                    { label: '按价格排序', value: 'price' },
                  ]}
                />
              </Col>
              <Col>
                <Text type="secondary" style={{ fontSize: 12, color: 'var(--muted)' }}>
                  评分 <span className="mono">{stats.scored}</span> 只 · 排除 <span className="mono">{stats.excluded}</span> · 耗时 <span className="mono">{stats.elapsed.toFixed(0)}</span>s
                </Text>
              </Col>
            </>
          )}
        </Row>
      </Card>

      {/* ── 选股结果 ── */}
      <Card
        style={{ borderRadius: 'var(--radius)', background: 'var(--surface)', borderColor: 'var(--border)' }}
        loading={loading}
        title={picks.length > 0 ? `选股结果 (Top ${picks.length})` : '等待选股'}
      >
        {sectorResonance.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ marginBottom: 8, fontWeight: 600, color: 'var(--fg)', fontFamily: 'var(--font-display)' }}>
              板块共振
            </div>
            <Table
              columns={sectorColumns}
              dataSource={sectorResonance}
              rowKey="sector"
              size="small"
              pagination={false}
              scroll={{ x: 630 }}
            />
          </div>
        )}
        <Table
          columns={columns}
          dataSource={sortedPicks}
          rowKey="code"
          size="small"
          rowSelection={{
            selectedRowKeys,
            onChange: setSelectedRowKeys,
          }}
          expandable={{
            expandedRowKeys: expandedRow ? [expandedRow] : [],
            onExpand: (expanded, record) => setExpandedRow(expanded ? record.code : null),
            expandedRowRender: (record: ScreenerPick) => (
              <div
                role="region"
                aria-label={`${record.code} 四轴解释`}
                style={{ padding: '8px 16px', background: 'var(--surface-2)', borderRadius: 'var(--radius-sm)' }}
              >
                <Space wrap size="small">
                  {[
                    { label: '技术面', val: record.factor_breakdown?.technical ?? (record.score ?? 0) * 0.35, color: 'var(--accent)' },
                    { label: '资金面', val: record.factor_breakdown?.money_flow ?? (record.score ?? 0) * 0.25, color: 'var(--down)' },
                    { label: '基本面', val: record.factor_breakdown?.fundamental ?? (record.score ?? 0) * 0.20, color: 'var(--warn)' },
                    { label: '情绪面', val: 0, color: 'var(--muted)' },
                    { label: 'AI预测', val: 0, color: 'var(--up)' },
                  ].map(d => (
                    <div key={d.label} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <Text style={{ fontSize: 11, width: 42, color: 'var(--fg-2)' }}>{d.label}</Text>
                      <div style={{ width: 80, height: 6, background: 'var(--border)', borderRadius: 3 }}>
                        <div
                          style={{
                            width: `${Math.min(100, (d.val / 25) * 100)}%`,
                            height: 6,
                            background: d.color,
                            borderRadius: 3
                          }}
                        />
                      </div>
                      <span className="mono" style={{ fontSize: 11 }}>{Number(d.val).toFixed(1)}</span>
                    </div>
                  ))}
                </Space>
                {record.entry_reason && (
                  <div style={{ marginTop: 8 }}>
                    <Text type="secondary" style={{ fontSize: 11, color: 'var(--muted)' }}>
                      <InfoCircleOutlined /> {record.entry_reason}
                    </Text>
                  </div>
                )}
                {hasFourAxisDetail(record) && (
                  <div style={{ marginTop: 10 }}>
                    <div style={{ marginTop: 8, display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                      {[
                        formatAxisScore('启动质量', record.factor_breakdown?.startup_quality ?? (record as unknown as { startup_quality_score?: number }).startup_quality_score),
                        formatAxisScore('点火爆发', record.factor_breakdown?.ignition_power ?? (record as unknown as { ignition_power_score?: number }).ignition_power_score),
                        formatAxisScore('硬科技', record.factor_breakdown?.hard_tech_conviction ?? (record.hard_tech?.tier ? 5 : 0)),
                      ].filter(Boolean).map(item => (
                        <Text key={item as string} style={{ fontSize: 12, color: 'var(--fg-2)' }}>{item}</Text>
                      ))}
                    </div>
                    {(record.risk_flags?.length || record.power_flags?.length) && (
                      <div style={{ marginTop: 8 }}>
                        <Space wrap size={[4, 4]}>
                          {(record.power_flags || []).map((flag: string) => (
                            <Tag
                              key={`power-${flag}`}
                              style={{ fontSize: 11, background: 'var(--down-bg)', borderColor: 'var(--down)', color: 'var(--down)' }}
                            >
                              {flag}
                            </Tag>
                          ))}
                          {(record.risk_flags || []).map((flag: string) => (
                            <Tag
                              key={`risk-${flag}`}
                              style={{ fontSize: 11, background: 'var(--warn-bg)', borderColor: 'var(--warn)', color: 'var(--warn)' }}
                            >
                              {flag}
                            </Tag>
                          ))}
                        </Space>
                      </div>
                    )}
                  </div>
                )}
                <div style={{ marginTop: 4 }}>
                  <Text type="secondary" style={{ fontSize: 11, color: 'var(--muted)' }}>
                    📊 综合评分 <span className="mono">{record.score?.toFixed(1)}</span> 分, 排名第 <span className="mono">{picks.findIndex((p) => p.code === record.code) + 1}/{picks.length}</span>, 评级 {record.grade} 级
                    {record.grade === 'S' ? ' — 技术面S级+资金面优秀+评分领先, 重点关注' : ''}
                    {record.grade === 'A' ? ' — 多维度表现均衡, 评分优良' : ''}
                    {record.grade === 'B' ? ' — 部分维度表现一般, 建议观察' : ''}
                  </Text>
                </div>
              </div>
            ),
          }}
          pagination={{ pageSize: mode === 'leader_afternoon_trend_full' ? 30 : 15, showSizeChanger: false }}
          scroll={{ x: 930 }}
          locale={{
            emptyText: (
              <div role="status" aria-live="polite">
                <Text type="secondary" style={{ color: 'var(--muted)' }}>
                  点击「开始选股」运行模型筛选全市场标的
                </Text>
              </div>
            )
          }}
        />
      </Card>

      {/* ── 底部声明 ── */}
      <div style={{ marginTop: 16, textAlign: 'center' }}>
        <Text type="secondary" style={{ fontSize: 12, color: 'var(--muted)' }}>
          © 2026 速赢AI · 选股结果基于历史数据与因子模型，不构成投资建议
        </Text>
      </div>
    </div>
  )
}
