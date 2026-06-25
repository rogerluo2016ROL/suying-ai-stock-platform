import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Row, Col, Card, Tag, Typography, Space, Button, Radio, List, Tabs,
  Progress, Tooltip, Modal, Table, Statistic, Badge, Divider, Empty, Result, message,
} from 'antd'
import {
  RiseOutlined, FallOutlined, SyncOutlined, ThunderboltOutlined,
  SearchOutlined, LineChartOutlined, StarOutlined, DashboardOutlined,
  BulbOutlined, ExperimentOutlined, FundOutlined, CheckCircleOutlined,
  InfoCircleOutlined, RightOutlined, ApiOutlined, BellOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import api, { signalApi } from '../api/client'

const { Title, Text } = Typography

// ── Types ──

interface SignalStock {
  code: string; name: string; price: number; change_pct: number
  volume: number; signal: string; desc: string; market: string
}

interface LimitStock {
  code: string; name: string; limit_price: number; change_pct: number; pre_close: number
}

interface WatchlistItem {
  code: string; name: string; market_cap: number; industry: string
}

interface ServiceHealth {
  key: string; name: string; port: number; online: boolean
}

interface ScreenerMode {
  id: string; name: string; cycle: string; style: string
}

interface AlertSignal {
  type: string; icon: string; level: string
  code: string; name: string; price: number; change_pct: number
  reason: string
}

interface AuctionIntentItem {
  code: string; name: string; auction_price: number; prev_close: number
  chg_pct: number; vs_vwap: number; vol_ratio: number; open_gap: number
  vol: number; amount: number
  intent: string; icon: string; level: string; score: number
  reasons: string[]
  breakdown: { price_direction: number; buy_sell_pressure: number; auction_strength: number; opening_continuity: number }
}

interface MarketSentimentData {
  score: number; label: string; trade_date: string
  avg_change_pct: number; up_stocks: number; down_stocks: number; total_stocks: number
  model: string; formula: string
  sub_dimensions: Record<string, string>
}

interface MarketRegimeData {
  regime: string; score: number; confidence: number; label: string
  dimensions?: Record<string, { score: number; weight: number; detail?: Record<string, unknown> }>
}

interface DashboardData {
  refreshed_at: string
  market_sentiment?: MarketSentimentData
  market_regime_v2?: MarketRegimeData
  signal_stocks: SignalStock[]
  limit_stocks: { up_count: number; down_count: number; up_list: LimitStock[]; down_list: LimitStock[]; data_source: string }
  alert_signals: AlertSignal[]
  auction_intent: { trade_date: string; total_analyzed: number; bullish_count: number; bearish_count: number; neutral_count: number; top_bullish: AuctionIntentItem[]; top_bearish: AuctionIntentItem[]; data_source: string }
  service_health: ServiceHealth[]
  screener_modes: ScreenerMode[]
  watchlist: WatchlistItem[]
  data_sources: Record<string, string>
}

// ── Signal color helpers (使用设计系统token) ──

function signalTag(signal: string) {
  if (signal === 'Bullish') return { color: 'var(--down)', icon: '📈', label: '看涨' } // A股红涨 → 绿表示涨
  if (signal === 'Bearish') return { color: 'var(--up)', icon: '📉', label: '看跌' }   // A股绿跌 → 红表示跌
  return { color: 'var(--accent)', icon: '➡️', label: '震荡' }
}

// ── Component ──

export default function Dashboard() {
  const navigate = useNavigate()
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)
  const [lastRefresh, setLastRefresh] = useState<string>('')
  const [limitModal, setLimitModal] = useState<{ open: boolean; type: 'up' | 'down' }>({ open: false, type: 'up' })

  // ── Screening Dashboard state ──
  const [dbSummary, setDbSummary] = useState<any>(null)
  const [dashboardPicks, setDashboardPicks] = useState<any[]>([])
  const [dashboardPredictions, setDashboardPredictions] = useState<any[]>([])
  const [picksLoading, setPicksLoading] = useState(false)
  const [dbLoading, setDbLoading] = useState(false)
  const [auctionPicks, setAuctionPicks] = useState<any[]>([])
  const [auctionSectors, setAuctionSectors] = useState<any[]>([])
  const [activeTab, setActiveTab] = useState('post')

  const fetchDashboard = useCallback(async () => {
    setLoading(true)
    try {
      // Cache-bust to ensure we always get fresh PG data
      const response = await signalApi.getDashboardSummary()
      const d = response.data as unknown as DashboardData
      setData(d)
      setError(false)
      setLastRefresh(new Date().toLocaleTimeString('zh-CN', { hour12: false }))
    } catch {
      // P1-11: surface the failure instead of silently rendering an empty board
      // (users couldn't distinguish "no data" from "load failed").
      setError(true)
    } finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchDashboard() }, [fetchDashboard])

  // Auto-refresh every 60s
  useEffect(() => {
    const timer = setInterval(fetchDashboard, 60_000)
    return () => clearInterval(timer)
  }, [fetchDashboard])

  // ── Fetch Screening Dashboard ──
  useEffect(() => {
    const fetchScreening = async () => {
      setPicksLoading(true); setDbLoading(true)
      try {
        const { data: d } = await api.get(`/dashboard/summary?_t=${Date.now()}`)
        if (d.status !== 'no_data') {
          setDbSummary(d)
          setDashboardPicks(d.dual_consensus?.length > 0 ? d.dual_consensus : d.merged || [])
          setDashboardPredictions(d.predictions || [])
        }
      } catch { /* silent */ }
      finally { setPicksLoading(false); setDbLoading(false) }
    }
    fetchScreening()
    const timer = setInterval(fetchScreening, 120_000)

    // 竞价数据
    api.get('/dashboard/auction')
      .then(({ data: d }) => {
        if (d.picks) { setAuctionPicks(d.picks); setAuctionSectors(d.sectors || []) }
      }).catch(() => {})

    // 自动切换 Tab: 9:25-14:00 竞价, 14:00-15:30 盘中, 其他盘后
    const h = new Date().getHours(), m = new Date().getMinutes()
    if (h === 9 || (h === 10 && m < 30)) setActiveTab('auction')
    else if (h >= 10 && h < 15) setActiveTab('intra')
    else setActiveTab('post')

    return () => clearInterval(timer)
  }, [])

  // ── Render helpers ──

  const marketRegime = data?.market_regime_v2
  const sentiment: MarketSentimentData | undefined = data?.market_sentiment || (marketRegime ? {
    score: marketRegime.score,
    label: marketRegime.label,
    trade_date: '',
    avg_change_pct: 0,
    up_stocks: 0,
    down_stocks: 0,
    total_stocks: 0,
    model: `市场状态 v2 · 置信度 ${marketRegime.confidence ?? '—'}`,
    formula: '趋势、宽度、流动性、杠杆、外资、估值、风险事件、情绪综合加权',
    sub_dimensions: Object.fromEntries(
      Object.entries(marketRegime.dimensions || {}).map(([key, dim]) => [
        key,
        `${Number(dim.score ?? 0).toFixed(1)}分 · 权重${Number((dim.weight ?? 0) * 100).toFixed(0)}%`,
      ]),
    ),
  } : undefined)
  const limitStocks = data?.limit_stocks
  const signalStocks = data?.signal_stocks || []
  const alertSignals = data?.alert_signals || []
  const auctionIntent = data?.auction_intent
  const watchlist = data?.watchlist || []
  const modes = data?.screener_modes || []
  const services = data?.service_health || []
  const onlineCount = services.filter(s => s.online).length
  const refreshCountdown = (d: string) => {
    if (!d) return ''
    const elapsed = Math.floor((Date.now() - new Date(d).getTime()) / 1000)
    const next = 60 - (elapsed % 60)
    return `${next}s 后自动刷新`
  }

  // Limit stock drill-down columns
  const limitColumns: ColumnsType<LimitStock> = [
    { title: '代码', dataIndex: 'code', width: 80, render: (v: string) => <Text code>{v}</Text> },
    { title: '名称', dataIndex: 'name', width: 100 },
    { title: '涨停价', dataIndex: 'limit_price', width: 80, render: (v: number) => `¥${v?.toFixed(2)}` },
    { title: '昨收', dataIndex: 'pre_close', width: 80, render: (v: number) => `¥${v?.toFixed(2)}` },
    { title: '涨幅', dataIndex: 'change_pct', width: 80,
      render: (v: number) => <Text className="mono" style={{ color: v >= 0 ? 'var(--up)' : 'var(--down)', fontWeight: 600 }}>{v >= 0 ? '+' : ''}{v}%</Text> },
  ]

  const sentimentColor = (sentiment?.score ?? 50) >= 60 ? 'var(--down)' : (sentiment?.score ?? 50) >= 40 ? 'var(--warn)' : 'var(--up)'

  const renderSignalCards = () => (
    <div style={{ overflow: 'hidden', position: 'relative' }}>
      {signalStocks.length > 0 ? (
        <div style={{
          display: 'flex', gap: 12, overflowX: 'auto', paddingBottom: 8,
          scrollBehavior: 'smooth',
        }}>
          {signalStocks.map(stock => {
            const st = signalTag(stock.signal)
            return (
              <Card key={stock.code} size="small" hoverable
                style={{ minWidth: 200, maxWidth: 200, borderRadius: 'var(--radius)', flexShrink: 0, border: '1px solid var(--border)' }}
                onClick={() => navigate(`/diagnosis?code=${stock.code}`)}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <Text strong style={{ fontSize: 14 }}>{stock.code}</Text>
                    <Text type="secondary" style={{ fontSize: 11, marginLeft: 6 }}>{stock.name}</Text>
                    <Tag style={{ marginLeft: 4, fontSize: 10 }}>{stock.market}</Tag>
                  </div>
                  <Tag color={st.color} style={{ fontSize: 10 }}>{st.icon} {st.label}</Tag>
                </div>
                <div style={{ marginTop: 8 }}>
                  <Text style={{ fontSize: 20, fontWeight: 700 }}>¥{stock.price}</Text>
                  <Text style={{ fontSize: 13, marginLeft: 8, color: stock.change_pct >= 0 ? 'var(--up)' : 'var(--down)' }}>
                    {stock.change_pct >= 0 ? '+' : ''}{stock.change_pct}%
                  </Text>
                </div>
                <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 4 }}>
                  {stock.desc || (stock.change_pct >= 0 ? '上涨' : '下跌')}
                </Text>
              </Card>
            )
          })}
        </div>
      ) : (
        <Card size="small" style={{ borderRadius: 8, textAlign: 'center' }}>
          <Text type="secondary">{data ? '暂无信号数据' : '信号数据加载中...'}</Text>
        </Card>
      )}
    </div>
  )

  const renderAlertSignalsCard = () => (
    <Card
      size="small"
      style={{ borderRadius: 'var(--radius)', height: '100%', borderTop: '3px solid var(--warn)', background: 'var(--warn-bg)' }}
      styles={{ body: { padding: '12px' } }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <Space size={4}>
          <BellOutlined style={{ color: '#fa8c16', fontSize: 14 }} />
          <Text strong style={{ fontSize: 13 }}>交易预警信号</Text>
          {alertSignals.length > 0 && (
            <Badge count={alertSignals.length} size="small" style={{ backgroundColor: '#fa8c16' }} />
          )}
        </Space>
        <Tooltip title={data?.data_sources?.alert_signals || '量价异动 + 涨跌停逼近实时预警'}>
          <InfoCircleOutlined style={{ color: 'var(--muted)', fontSize: 11, cursor: 'help' }} />
        </Tooltip>
      </div>

      {alertSignals.length > 0 ? (
        <div style={{
          maxHeight: 110, overflowY: 'auto',
          scrollBehavior: 'smooth',
        }}>
          {alertSignals.map((a, i) => (
            <div
              key={`${a.code}-${i}`}
              style={{
                padding: '5px 6px', marginBottom: 4, borderRadius: 4,
                background: a.level === 'urgent' ? 'var(--up-bg)' : 'var(--warn-bg)',
                borderLeft: `3px solid ${a.level === 'urgent' ? 'var(--up)' : 'var(--warn)'}`,
                cursor: 'pointer', fontSize: 11,
                animation: i === 0 ? 'pulse 2s infinite' : undefined,
              }}
              onClick={() => navigate(`/diagnosis?code=${a.code}`)}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <Space size={4}>
                  <span>{a.icon}</span>
                  <Text strong style={{ fontSize: 11 }}>{a.code}</Text>
                  <Text style={{ fontSize: 10, color: '#595959' }}>{a.name}</Text>
                  <Text style={{
                    fontSize: 11, fontWeight: 600,
                    color: a.change_pct >= 0 ? '#52c41a' : '#ff4d4f',
                  }}>
                    {a.change_pct >= 0 ? '+' : ''}{a.change_pct}%
                  </Text>
                </Space>
                <Tag color={a.level === 'urgent' ? 'red' : 'orange'}
                     style={{ fontSize: 9, margin: 0, padding: '0 4px', lineHeight: '16px' }}>
                  {a.level === 'urgent' ? '紧急' : '预警'}
                </Tag>
              </div>
              <Text type="secondary" style={{ fontSize: 10, display: 'block', marginTop: 2, lineHeight: 1.4 }}>
                {a.reason}
              </Text>
            </div>
          ))}
        </div>
      ) : (
        <div style={{ textAlign: 'center', padding: '12px 0' }}>
          <CheckCircleOutlined style={{ fontSize: 20, color: 'var(--down)', display: 'block', marginBottom: 4 }} />
          <Text type="secondary" style={{ fontSize: 11 }}>暂无异常预警信号</Text>
        </div>
      )}

      <Divider style={{ margin: '6px 0' }} />
      <div style={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
        {services.map(s => (
          <Tooltip key={s.key} title={`${s.name} (:${s.port}) ${s.online ? '在线' : '离线'}`}>
            <Badge status={s.online ? 'success' : 'default'} />
            <Text style={{ fontSize: 9, color: 'var(--muted)', marginRight: 4 }}>:{s.port}</Text>
          </Tooltip>
        ))}
      </div>
    </Card>
  )

  const renderMarketSentimentTab = () => (
    <Row gutter={12}>
      <Col xs={24} lg={12}>
        <Tooltip
          title={
            <div style={{ maxWidth: 360 }}>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>市场情绪指数 ({sentiment?.score ?? '—'})</div>
              <div style={{ fontSize: 12, marginBottom: 8 }}>{sentiment?.model}</div>
              <div style={{ fontSize: 12, marginBottom: 4 }}>{sentiment?.formula}</div>
              <div style={{ fontSize: 11, color: '#aaa' }}>
                {sentiment?.sub_dimensions && Object.entries(sentiment.sub_dimensions).map(([k, v]) => (
                  <div key={k}>{k}: {v}</div>
                ))}
              </div>
            </div>
          }
        >
          <Card size="small" style={{ borderRadius: 8, cursor: 'help', height: '100%' }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              市场情绪 <InfoCircleOutlined style={{ fontSize: 10 }} />
            </Text>
            <div style={{ fontSize: 24, fontWeight: 700, color: sentimentColor }}>
              {sentiment?.score ?? '—'}
              <Text style={{ fontSize: 13, fontWeight: 400, marginLeft: 6, color: sentimentColor }}>
                {sentiment?.label}
              </Text>
            </div>
            <Progress percent={sentiment?.score ?? 50} size="small" showInfo={false}
              strokeColor={sentimentColor} />
            {sentiment?.trade_date && (
              <Text type="secondary" style={{ fontSize: 10 }}>
                数据日期: {sentiment.trade_date} | 共 {sentiment.total_stocks} 只
              </Text>
            )}
          </Card>
        </Tooltip>
      </Col>
      <Col xs={24} lg={12}>
        <Card size="small" style={{ borderRadius: 8, cursor: 'pointer', height: '100%' }}
          onClick={() => setLimitModal({ open: true, type: 'up' })} hoverable>
          <Text type="secondary" style={{ fontSize: 12 }}>
            涨停 / 跌停 <InfoCircleOutlined style={{ fontSize: 10 }} />
          </Text>
          <div style={{ fontSize: 24, fontWeight: 700 }}>
            <Tooltip title="点击查看涨停股票列表">
              <span style={{ color: 'var(--up)', cursor: 'pointer' }}
                onClick={e => { e.stopPropagation(); setLimitModal({ open: true, type: 'up' }) }}>
                {limitStocks?.up_count ?? '—'}
              </span>
            </Tooltip>
            <span style={{ color: 'var(--muted)', margin: '0 6px' }}>/</span>
            <Tooltip title="点击查看跌停股票列表">
              <span style={{ color: 'var(--down)', cursor: 'pointer' }}
                onClick={e => { e.stopPropagation(); setLimitModal({ open: true, type: 'down' }) }}>
                {limitStocks?.down_count ?? '—'}
              </span>
            </Tooltip>
          </div>
          <Text type="secondary" style={{ fontSize: 10 }}>
            {limitStocks?.data_source || '数据来源: stk_limit 表'}
          </Text>
        </Card>
      </Col>
    </Row>
  )

  const renderAuctionIntentTab = () => (
    <Card
      title={<Space><ThunderboltOutlined style={{ color: 'var(--warn)' }} />竞价意图</Space>}
      size="small" style={{ borderRadius: 8 }}
      extra={
        auctionIntent && (
          <Space size={4}>
            <Tag color="red" style={{ fontSize: 10, margin: 0 }}>🔥{auctionIntent.bullish_count}</Tag>
            <Tag color="green" style={{ fontSize: 10, margin: 0 }}>⚠️{auctionIntent.bearish_count}</Tag>
          </Space>
        )
      }
    >
      {auctionIntent ? (
        <div>
          {auctionIntent.top_bullish?.slice(0, 6).map((item: AuctionIntentItem) => (
            <div key={item.code} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '6px 0', borderBottom: '1px solid #f5f5f5', cursor: 'pointer',
            }} onClick={() => navigate(`/diagnosis?code=${item.code}`)}>
              <Space size={4}>
                <Text style={{ fontSize: 10 }}>{item.icon}</Text>
                <Text strong style={{ fontSize: 12 }}>{item.code}</Text>
                <Text style={{ fontSize: 11, color: '#595959' }}>{item.name}</Text>
              </Space>
              <Space size={4}>
                <Text style={{
                  fontSize: 12, fontWeight: 600,
                  color: item.chg_pct >= 0 ? '#cf1322' : '#3f8600',
                }}>
                  {item.chg_pct >= 0 ? '+' : ''}{item.chg_pct}%
                </Text>
                <Tag color={item.score >= 75 ? 'red' : item.score >= 60 ? 'orange' : 'default'}
                     style={{ fontSize: 9, margin: 0, padding: '0 3px' }}>
                  {item.score}
                </Tag>
              </Space>
            </div>
          ))}
          {auctionIntent.top_bearish?.slice(0, 4).map((item: AuctionIntentItem) => (
            <div key={item.code} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '6px 0', cursor: 'pointer',
            }} onClick={() => navigate(`/diagnosis?code=${item.code}`)}>
              <Space size={4}>
                <Text style={{ fontSize: 10 }}>{item.icon}</Text>
                <Text style={{ fontSize: 12, color: '#8c8c8c' }}>{item.code}</Text>
                <Text style={{ fontSize: 11, color: '#bfbfbf' }}>{item.name}</Text>
              </Space>
              <Space size={4}>
                <Text style={{ fontSize: 12, color: '#3f8600' }}>
                  {item.chg_pct >= 0 ? '+' : ''}{item.chg_pct}%
                </Text>
                <Tag color="green" style={{ fontSize: 9, margin: 0, padding: '0 3px' }}>{item.score}</Tag>
              </Space>
            </div>
          ))}
          <Divider style={{ margin: '8px 0' }} />
          <Text type="secondary" style={{ fontSize: 10 }}>
            分析 {auctionIntent.total_analyzed}只 · 模型: 价格方向+买卖压力+竞价强度+开盘延续
          </Text>
        </div>
      ) : (
        <Text type="secondary" style={{ fontSize: 11 }}>竞价数据加载中...</Text>
      )}
    </Card>
  )

  const renderWatchlistTab = () => (
    <Card
      title={<Space><StarOutlined />自选监控</Space>}
      size="small"
      style={{ borderRadius: 8 }}
      extra={<Button size="small" type="text" icon={<SyncOutlined />} loading={loading} onClick={fetchDashboard} />}
    >
      {watchlist.length > 0 ? (
        <div>
          {watchlist.map(s => (
            <div key={s.code} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '8px 0', borderBottom: '1px solid var(--border)', cursor: 'pointer',
            }} onClick={() => navigate(`/diagnosis?code=${s.code}`)}>
              <div>
                <Text strong style={{ fontSize: 13 }}>{s.code}</Text>
                <Text style={{ fontSize: 12, marginLeft: 6 }}>{s.name}</Text>
              </div>
              <div style={{ textAlign: 'right' }}>
                <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>
                  {s.industry || '—'}
                </Text>
                <Text style={{ fontSize: 12, fontWeight: 600 }}>
                  {(s.market_cap / 1e8).toFixed(0)}亿
                </Text>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <Empty description={data ? '暂无自选股数据' : '自选股加载中...'} image={Empty.PRESENTED_IMAGE_SIMPLE} />
      )}
      <div style={{ marginTop: 8 }}>
        <Text type="secondary" style={{ fontSize: 11 }}>
          数据来源: {data?.data_sources?.watchlist || 'PG stocks 表市值 Top 10'}
        </Text>
      </div>
    </Card>
  )

  const renderServiceHealthCard = () => (
    <Card
      title={<Space><DashboardOutlined />服务状态详情</Space>}
      size="small" style={{ borderRadius: 8 }}
      extra={<Text type="secondary" style={{ fontSize: 11 }}>{onlineCount}/{services.length}</Text>}
    >
      {services.map(s => (
        <div key={s.key} style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '5px 0', fontSize: 12,
        }}>
          <Space size="small">
            <Badge status={s.online ? 'success' : 'default'} />
            <Text style={{ fontSize: 12 }}>{s.name}</Text>
          </Space>
          <Space size="small">
            <Tag color={s.online ? 'success' : 'default'} style={{ fontSize: 10 }}>
              :{s.port}
            </Tag>
            <Text type="secondary" style={{ fontSize: 10 }}>
              {s.online ? '在线' : '离线'}
            </Text>
          </Space>
        </div>
      ))}
      <Divider style={{ margin: '8px 0' }} />
      <Text type="secondary" style={{ fontSize: 10 }}>
        检测方式: 各服务 /api/v1/health 端点 · 60秒自动刷新
      </Text>
    </Card>
  )

  const renderSmartDashboardTabs = () => (
    <Card style={{ borderRadius: 8, marginBottom: 16 }}>
      <Tabs
        renderTabBar={(props, DefaultTabBar) => (
          <DefaultTabBar {...props} aria-label="智能看板二级菜单" />
        )}
        items={[
          { key: 'market-sentiment', label: '市场情绪', children: renderMarketSentimentTab() },
          { key: 'auction-intent', label: '竞价意图', children: renderAuctionIntentTab() },
          {
            key: 'signal-overview',
            label: '信号总览',
            children: (
              <Space direction="vertical" size={12} style={{ width: '100%' }}>
                {renderSignalCards()}
                <Row gutter={12}>
                  <Col xs={24} lg={14}>{renderAlertSignalsCard()}</Col>
                  <Col xs={24} lg={10}>{renderServiceHealthCard()}</Col>
                </Row>
              </Space>
            ),
          },
          { key: 'watchlist-tracking', label: '自选跟踪', children: renderWatchlistTab() },
        ]}
      />
    </Card>
  )

  return (
    <div>
      {/* P1-11: explicit failure state so an empty board is distinguishable from a load error. */}
      {error && !data && !loading && (
        <Result
          status="warning"
          title="看板加载失败"
          subTitle="无法连接数据服务，请稍后重试。"
          extra={
            <Button type="primary" icon={<SyncOutlined />} onClick={fetchDashboard}>
              重试
            </Button>
          }
        />
      )}
      {/* ══════════════════════════════════════════════════ */}
      {/* ── Header: AI Opportunity Radar ── */}
      {/* ══════════════════════════════════════════════════ */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>
            <ThunderboltOutlined style={{ marginRight: 8, color: 'var(--accent)' }} />
            AI 机会雷达
          </Title>
          {data?.data_sources?.signal_stocks && (
            <Tooltip title={`数据来源: ${data.data_sources.signal_stocks}`}>
              <Text type="secondary" style={{ fontSize: 11 }}>
                <InfoCircleOutlined style={{ marginRight: 4 }} />
                {data?.data_sources?.signal_stocks?.split('—')[0]?.trim()}
              </Text>
            </Tooltip>
          )}
        </div>
        <Space>
          {lastRefresh && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              最近刷新: {lastRefresh}
              {data?.refreshed_at && (
                <Text type="secondary" style={{ fontSize: 10, marginLeft: 8, color: 'var(--muted)' }}>
                  ({refreshCountdown(data.refreshed_at)})
                </Text>
              )}
            </Text>
          )}
          <Button size="small" icon={<SyncOutlined />} loading={loading} onClick={fetchDashboard}>刷新</Button>
        </Space>
      </div>

      {renderSmartDashboardTabs()}

      {/* ══════════════════════════════════════════════════ */}
      {/* ── Main Content ── */}
      {/* ══════════════════════════════════════════════════ */}
      <Row gutter={16}>
        <Col span={24}>
          {/* ── AI Analysis Engine ── */}
          <Card
            title={<Space><StarOutlined style={{ color: 'var(--accent)' }} />AI 分析引擎</Space>}
            extra={<Tag color="blue">AI-POWERED</Tag>}
            style={{ borderRadius: 8, marginBottom: 16 }}
          >
            <Text type="secondary">
              多源数据驱动 · 机构级洞察 · 实时市场脉动 · 点击卡片进入对应功能
            </Text>
            <Row gutter={12} style={{ marginTop: 16 }}>
              <Col span={8}>
                <Card size="small" hoverable style={{ textAlign: 'center', borderRadius: 8, cursor: 'pointer' }}
                  onClick={() => navigate('/predictions')}>
                  <LineChartOutlined style={{ fontSize: 28, color: 'var(--accent)' }} />
                  <div style={{ fontWeight: 600, marginTop: 8 }}>K线预测</div>
                  <Text type="secondary" style={{ fontSize: 11 }}>Kronos 4时间维度AI共识</Text>
                  <div style={{ marginTop: 4 }}>
                    <Button type="link" size="small">进入预测 <RightOutlined /></Button>
                  </div>
                </Card>
              </Col>
              <Col span={8}>
                <Card size="small" hoverable style={{ textAlign: 'center', borderRadius: 8, cursor: 'pointer' }}
                  onClick={() => navigate('/screener')}>
                  <SearchOutlined style={{ fontSize: 28, color: 'var(--accent)' }} />
                  <div style={{ fontWeight: 600, marginTop: 8 }}>智能选股</div>
                  <Text type="secondary" style={{ fontSize: 11 }}>6套策略 · 5000+标的 · 多因子排序</Text>
                  <div style={{ marginTop: 4 }}>
                    <Button type="link" size="small">进入选股 <RightOutlined /></Button>
                  </div>
                </Card>
              </Col>
              <Col span={8}>
                <Card size="small" hoverable style={{ textAlign: 'center', borderRadius: 8, cursor: 'pointer' }}
                  onClick={() => navigate('/strategy')}>
                  <BulbOutlined style={{ fontSize: 28, color: 'var(--accent)' }} />
                  <div style={{ fontWeight: 600, marginTop: 8 }}>方案管理</div>
                  <Text type="secondary" style={{ fontSize: 11 }}>选股 → 方案 → 自动交易</Text>
                  <div style={{ marginTop: 4 }}>
                    <Button type="link" size="small">进入方案 <RightOutlined /></Button>
                  </div>
                </Card>
              </Col>
            </Row>
          </Card>

          {/* ── Screening Models ── */}
          <Card
            title={<Space><ExperimentOutlined style={{ color: 'var(--accent)' }} />选股模型 ({modes.length})</Space>}
            style={{ borderRadius: 8, marginBottom: 16 }}
            extra={
              <Tooltip title={data?.data_sources?.screener_modes}>
                <InfoCircleOutlined style={{ color: 'var(--muted)' }} />
              </Tooltip>
            }
          >
            {modes.length > 0 ? (
              <List
                dataSource={modes}
                renderItem={(m: ScreenerMode) => (
                  <List.Item style={{ padding: '8px 0', cursor: 'pointer' }}
                    onClick={() => navigate('/screener')}>
                    <Space>
                      <Tag color="blue" style={{ fontFamily: 'monospace' }}>{m.id}</Tag>
                      <Text strong>{m.name}</Text>
                      <Tag>{m.cycle}</Tag>
                      <Tag style={{ color: m.style === '激进' ? 'var(--up)' : m.style === '稳健' ? 'var(--down)' : 'var(--accent)', borderColor: m.style === '激进' ? 'var(--up)' : m.style === '稳健' ? 'var(--down)' : 'var(--accent)' }}>
                        {m.style}
                      </Tag>
                    </Space>
                  </List.Item>
                )}
              />
            ) : (
              <Empty description="选股模型加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>

          {/* ── Market Data Sources ── */}
          <Card size="small" style={{ borderRadius: 'var(--radius)', background: 'var(--surface-2)' }}
            title={<Space><ApiOutlined style={{ color: 'var(--muted)' }} />数据来源</Space>}>
            {data?.data_sources && Object.entries(data.data_sources).map(([key, val]) => (
              <div key={key} style={{ fontSize: 12, marginBottom: 2 }}>
                <Text type="secondary" style={{ fontFamily: 'monospace', fontSize: 11 }}>{key}</Text>
                <Text style={{ fontSize: 11, marginLeft: 8 }}>{val}</Text>
              </div>
            ))}
          </Card>
        </Col>
      </Row>

      {/* ══════════════════════════════════════════════════ */}
      {/* ── Smart Screening Dashboard ── */}
      {/* ══════════════════════════════════════════════════ */}
      <Card
        title={<Space><SearchOutlined style={{ color: '#1677ff' }} />多策略融合选股看板</Space>}
        style={{ borderRadius: 8, marginBottom: 16 }}
        extra={<Space>
          <Text type="secondary" style={{ fontSize: 11 }}>数据来源: orchestrator.py</Text>
          <Button size="small" type="primary" icon={<ThunderboltOutlined />}
            onClick={async () => {
              try {
                await api.post('/dashboard/run-pipeline')
                message.success('流水线已触发, 2分钟后刷新查看结果')
              } catch { message.error('触发失败') }
            }}>
            一键选股
          </Button>
        </Space>}
      >
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
          // ── Tab 1: 竞价 ──
          { key: 'auction', label: '🔥 竞价选股',
            children: (
              <Row gutter={16}>
                <Col span={16}>
                  <Table dataSource={auctionPicks.slice(0,15)} rowKey="code" size="small" pagination={false}
                    scroll={{ y: 350 }}
                    onRow={r => ({ onClick: () => navigate(`/diagnosis?code=${r.code}`), style: {cursor:'pointer'} })}
                    columns={[
                      { title:'#', width:30, render:(_:any,__:any,i:number) => i+1 },
                      { title:'代码', dataIndex:'code', width:80, render:(v:string) => <Text code>{v}</Text> },
                      { title:'高开', dataIndex:'gap_pct', width:70, render:(v:number) => <Text style={{color:v>=5?'#cf1322':'#fa8c16',fontWeight:600}}>+{v}%</Text> },
                      { title:'评分', dataIndex:'score', width:50, sorter:(a:any,b:any)=>a.score-b.score },
                      { title:'现价', dataIndex:'price', width:60 },
                      { title:'板块', dataIndex:'industry', width:80 },
                    ]}
                  />
                </Col>
                <Col span={8}>
                  <Card size="small" style={{borderRadius:8,marginBottom:8}}>
                    <Statistic title="竞价标的" value={auctionPicks.length} suffix="只" valueStyle={{fontSize:18}} />
                  </Card>
                  <Card size="small" title="🔥 一字定方向" style={{borderRadius:8}}>
                    {auctionSectors.slice(0,6).map((s:any) => (
                      <div key={s.name} style={{display:'flex',justifyContent:'space-between',padding:'2px 0',fontSize:12}}>
                        <span>{s.name}</span>
                        <Tag color={s.count>=5?'red':s.count>=3?'orange':'default'}>{s.count}只</Tag>
                      </div>
                    ))}
                  </Card>
                </Col>
              </Row>
            )
          },
          // ── Tab 2: 盘中 ──
          { key: 'intra', label: '📈 盘中选股',
            children: (
              <div style={{textAlign:'center',padding:20}}>
                <Text type="secondary">盘中选股需在 14:00 运行 leader_scalp_intraday.py</Text>
                <br/>
                <Button size="small" style={{marginTop:8}} icon={<ThunderboltOutlined />}
                  onClick={() => window.open('/api/v1/dashboard/run-pipeline','_blank')}>
                  触发盘中选股
                </Button>
              </div>
            )
          },
          // ── Tab 3: 盘后 ──
          { key: 'post', label: '📊 盘后选股',
            children: (
        <Row gutter={16}>
          <Col span={16}>
            <Text strong style={{ fontSize: 13 }}>共识选股 Top 20</Text>
            <Table
              dataSource={dashboardPicks.slice(0, 20)}
              rowKey="code"
              size="small"
              loading={dbLoading || picksLoading}
              pagination={false}
              scroll={{ y: 400 }}
              style={{ marginTop: 8 }}
              onRow={(record) => ({
                onClick: () => navigate(`/diagnosis?code=${record.code}`),
                style: { cursor: 'pointer' },
              })}
              columns={[
                { title: '#', width: 30, render: (_: any, __: any, i: number) => i + 1 },
                { title: '代码', dataIndex: 'code', width: 80, render: (v: string) => <Text code>{v}</Text> },
                { title: '名称', dataIndex: 'name', width: 80 },
                { title: '共识', dataIndex: 'consensus_level', width: 120,
                  render: (v: string, r: any) => (
                    <Space>
                      <Tag color={r.consensus >= 2 ? 'gold' : 'default'}>{v}</Tag>
                      <Text type="secondary" style={{ fontSize: 10 }}>{r.sources?.join?.('+')}</Text>
                    </Space>
                  )},
                { title: '评分', dataIndex: 'best_score', width: 60, sorter: (a:any,b:any) => a.best_score - b.best_score,
                  render: (v: number) => <Text strong>{v}</Text> },
                { title: '评级', dataIndex: 'best_grade', width: 50,
                  render: (v: string) => <Tag color={v==='S'?'red':v==='A'?'orange':'default'}>{v}</Tag> },
              ]}
            />
          </Col>

          {/* Right: Summary stats + Predictions */}
          <Col span={8}>
            {/* Summary stats */}
            <Card size="small" style={{ borderRadius: 8, marginBottom: 12 }}>
              <Statistic title="融合标的" value={dbSummary?.summary?.total_picks || 0} suffix="只"
                valueStyle={{ fontSize: 20 }} />
              <Row gutter={8}>
                <Col span={12}>
                  <Statistic title="高共识" value={dbSummary?.summary?.consensus_dual || 0}
                    valueStyle={{ fontSize: 16, color: '#faad14' }} suffix="只" />
                </Col>
                <Col span={12}>
                  <Statistic title="策略数" value={dbSummary?.summary?.strategies_run || 0}
                    valueStyle={{ fontSize: 16, color: '#1677ff' }} suffix="套" />
                </Col>
              </Row>
              <Text type="secondary" style={{ fontSize: 10 }}>
                耗时 {(dbSummary?.elapsed || 0).toFixed(0)}s · {dbSummary?.date || '—'}
              </Text>
            </Card>

            {/* Kronos Predictions */}
            <Card size="small" title={<Space><LineChartOutlined style={{ color: '#722ed1' }} />AI 预测 Top 5</Space>}
              style={{ borderRadius: 8 }}>
              {dashboardPredictions.slice(0, 5).map((p: any) => (
                <div key={p.code} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '6px 0', borderBottom: '1px solid #f0f0f0', fontSize: 12,
                }}>
                  <div>
                    <Text strong style={{ fontSize: 12 }}>{p.code}</Text>
                    <Text style={{ marginLeft: 4, fontSize: 11 }}>{p.name}</Text>
                  </div>
                  <Space size={4}>
                    <Tag color={p.pred_return_pct > 0 ? 'green' : 'red'} style={{ fontSize: 10 }}>
                      {p.pred_return_pct > 0 ? '+' : ''}{p.pred_return_pct}%
                    </Tag>
                    <Text style={{ fontSize: 10, color: '#8c8c8c' }}>{p.current_price}</Text>
                  </Space>
                </div>
              ))}
              {dashboardPredictions.length === 0 && (
                <Text type="secondary" style={{ fontSize: 11 }}>预测模型未加载或无可预测标的</Text>
              )}
              {dbSummary?.summary?.predictions_total > 0 && (
                <Text type="secondary" style={{ fontSize: 9, display: 'block', marginTop: 4 }}>
                  Kronos-mini 微调模型 · {dbSummary.summary.predictions_up}↑ {dbSummary.summary.predictions_down}↓
                </Text>
              )}
            </Card>
          </Col>
        </Row>
            )
          },
        ]} />
      </Card>

      {/* ══════════════════════════════════════════════════ */}
      {/* ── Limit Stock Drill-Down Modal ── */}
      {/* ══════════════════════════════════════════════════ */}
      <Modal
        title={`${limitModal.type === 'up' ? '📈 涨停' : '📉 跌停'} 股票列表 (${limitModal.type === 'up' ? limitStocks?.up_count : limitStocks?.down_count} 只)`}
        open={limitModal.open}
        onCancel={() => setLimitModal({ open: false, type: 'up' })}
        footer={null}
        width={600}
      >
        <Radio.Group
          value={limitModal.type}
          onChange={e => setLimitModal(prev => ({ ...prev, type: e.target.value }))}
          style={{ marginBottom: 16 }}
        >
          <Radio.Button value="up">涨停 ({limitStocks?.up_count ?? 0})</Radio.Button>
          <Radio.Button value="down">跌停 ({limitStocks?.down_count ?? 0})</Radio.Button>
        </Radio.Group>
        {limitModal.type === 'up' && (limitStocks?.up_list?.length ?? 0) > 0 && (
          <Table columns={limitColumns} dataSource={limitStocks!.up_list} rowKey="code"
            size="small" pagination={{ pageSize: 15 }} />
        )}
        {limitModal.type === 'down' && (limitStocks?.down_list?.length ?? 0) > 0 && (
          <Table columns={limitColumns} dataSource={limitStocks!.down_list} rowKey="code"
            size="small" pagination={{ pageSize: 15 }} />
        )}
        {((limitModal.type === 'up' && !limitStocks?.up_list?.length) ||
          (limitModal.type === 'down' && !limitStocks?.down_list?.length)) && (
          <Empty description="暂无数据。stk_limit 表可能缺少当日的涨跌停明细。" />
        )}
      </Modal>
    </div>
  )
}
