import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  BarChartOutlined,
  CheckCircleOutlined,
  FireOutlined,
  FundOutlined,
  LineChartOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons'
import { screenerApi } from '../../api/client'
import { message } from 'antd'
import { MetricCard, PrototypeCard, SegmentTabs } from '../../components/prototype'
import { num } from './helpers'
import type { AuctionRow, CandidateRow, SectorRow } from './types'

export default function AuctionTab({
  loading,
  error,
  bullishRows,
  bearishRows,
  candidateRows,
  sectorRows,
  auction,
  tradeDate,
  onRefresh,
}: {
  loading: boolean
  error: string
  bullishRows: AuctionRow[]
  bearishRows: AuctionRow[]
  candidateRows: CandidateRow[]
  sectorRows: SectorRow[]
  auction: Record<string, unknown>
  tradeDate?: string
  onRefresh: () => Promise<void>
}) {
  const navigate = useNavigate()
  const totalCount = num(auction.total_count ?? auction.total ?? auction.count, bullishRows.length + bearishRows.length)
  const firstBullish = bullishRows[0]

  // 竞价子页签：纯前端 state 切换，对照 preview switchSubTab。overview/stock 有内容；
  // bond/detail 暂无内容面板，点击仅切高亮（preview 同此，不调 API）。
  const [auctionSubTab, setAuctionSubTab] = useState('overview')
  // 表格行勾选：抢筹表 / 出货表分别维护 Set<code>。
  const [selectedBullish, setSelectedBullish] = useState<Set<string>>(new Set())
  const [selectedBearish, setSelectedBearish] = useState<Set<string>>(new Set())
  // 已锁定板块（点板块卡/右栏选股-> 写入）。
  const [selectedSector, setSelectedSector] = useState<string | null>(null)
  // 局部刷新 / 候选池写入 / 自选写入 三态。
  const [refreshing, setRefreshing] = useState(false)
  const [recordingPool, setRecordingPool] = useState(false)
  const [watchingCode, setWatchingCode] = useState<string>('')

  const handleRefresh = async () => {
    if (refreshing) return
    setRefreshing(true)
    try {
      await onRefresh()
    } finally {
      setRefreshing(false)
    }
  }

  const toggleBullish = (code: string) => {
    setSelectedBullish(prev => {
      const next = new Set(prev)
      if (next.has(code)) next.delete(code)
      else next.add(code)
      return next
    })
  }
  const toggleBearish = (code: string) => {
    setSelectedBearish(prev => {
      const next = new Set(prev)
      if (next.has(code)) next.delete(code)
      else next.add(code)
      return next
    })
  }

  // 加入候选池：抢筹表选中标的 → screenerApi.recordCandidatePool（payload 参 Screener.tsx:930 + types.ts:1172 契约）。
  const handleAddBullishToPool = async () => {
    if (recordingPool || selectedBullish.size === 0) return
    const picks = bullishRows.filter(row => selectedBullish.has(row.code))
    const candidates = picks.map((row, index) => ({
      code: row.code,
      name: row.name,
      score: Number(row.score) || undefined,
      grade: 'A',
      rank: index + 1,
    }))
    setRecordingPool(true)
    try {
      const response = await screenerApi.recordCandidatePool({
        source_module: 'open-decision',
        source_mode: 'auction_bullish',
        name: `竞价抢筹-${tradeDate || '最新'}`,
        candidates,
        trade_date: tradeDate,
      })
      const poolId = response.data?.pool_id
      message.success(`已写入候选池${poolId ? `（${poolId}）` : ''}：${candidates.length} 只`)
      setSelectedBullish(new Set())
      screenerApi
        .queryCandidatePool({ source_module: 'open-decision', page: 1, page_size: 50 })
        .catch(() => message.error('刷新候选池计数失败，请手动刷新'))
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      message.error(detail || '候选池写入失败，请稍后重试')
    } finally {
      setRecordingPool(false)
    }
  }

  // 加入观察：出货表选中标的 → screenerApi.addWatchlist（参 CandidatePool handleWatch:1102 模式）。
  const handleAddBearishToWatch = async () => {
    if (watchingCode || selectedBearish.size === 0) return
    const picks = bearishRows.filter(row => selectedBearish.has(row.code))
    setWatchingCode('batch')
    try {
      let ok = 0
      let lastReason = ''
      for (const row of picks) {
        const response = await screenerApi.addWatchlist({ code: row.code, name: row.name })
        if (response.data?.record) ok += 1
        else if (response.data?.fallback_reason) lastReason = response.data.fallback_reason
      }
      if (ok > 0) message.success(`已加入自选：${ok} 只`)
      if (lastReason) message.error(lastReason)
      setSelectedBearish(new Set())
      screenerApi.listWatchlist().catch(() => message.error('刷新自选列表失败，请手动刷新'))
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      message.error(detail || '加入自选失败，请稍后重试')
    } finally {
      setWatchingCode('')
    }
  }

  const selectSector = (name: string) => {
    setSelectedSector(name)
    setAuctionSubTab('stock')
  }

  return (
    <div className="od-auction-layout">
      <div className="od-auction-main">
        <section className="od-engine card">
          <div>
            <span className="led on" />
            <strong>竞价分析引擎</strong>
            <span className="mono">dashboard/auction</span>
            <span className="tag t-down">{loading ? '加载中' : '已刷新'}</span>
            <span className="tag t-neu">{totalCount} 只标的</span>
          </div>
          <div>
            <span className="prototype-panel-note">{error || '最近刷新来自 dashboard/auction 与 signal/live'}</span>
            <button type="button" className="btn sm ghost" onClick={handleRefresh} disabled={refreshing} title={refreshing ? '刷新中…' : '重新拉取竞价数据'}>{refreshing ? '刷新中…' : '刷新'}</button>
          </div>
        </section>

        <section className="od-risk-callout">
          <div className="od-risk-icon">!</div>
          <div>
            <div className="od-risk-title">竞价风险提示 · 高开过热板块需二次确认</div>
            <div className="prototype-panel-note">
              {sectorRows.length
                ? `${sectorRows.slice(0, 2).map(row => row.name).join('、')} 当前竞价共振靠前；若开盘 5 分钟量价不能延续，候选池标的进入信号扫描复核。`
                : '暂无实时板块共振，等待 dashboard/auction 与 signal/live 返回。'}
            </div>
          </div>
          <div className="od-risk-actions">
            <button type="button" className="btn sm ghost" onClick={() => navigate('/signals')} title="跳转信号总览查看全盘意图">查看意图全景</button>
            <button type="button" className="btn sm primary" onClick={() => setAuctionSubTab('stock')} title="切到竞价选股子页签">进入竞价选股</button>
          </div>
        </section>

        <div className="od-subtabs">
          <SegmentTabs
            ariaLabel="竞价分析子页签"
            activeKey={auctionSubTab}
            onChange={setAuctionSubTab}
            items={[
              { key: 'overview', label: '竞价意图全景' },
              { key: 'stock', label: '竞价选股' },
              { key: 'bond', label: '可转债竞价' },
              { key: 'detail', label: '全量明细' },
            ]}
          />
        </div>

        <div className="kpis od-auction-kpis">
          <MetricCard label="分析标的" value={String(totalCount)} sub="dashboard/auction" tone="muted" />
          <MetricCard label="强烈抢筹" value={String(bullishRows.filter(row => row.score >= 75).length)} sub="评分 >= 75" tone="up" />
          <MetricCard label="偏多抢筹" value={String(bullishRows.filter(row => row.score < 75).length)} sub="评分 60-74" tone="warn" />
          <MetricCard label="中性观察" value={String(Math.max(0, totalCount - bullishRows.length - bearishRows.length))} sub="等待开盘确认" tone="accent" />
          <MetricCard label="出货预警" value={String(bearishRows.length)} sub="偏空/强出货" tone="down" />
          <MetricCard label="候选池" value={String(candidateRows.length)} sub="已入池待复核" tone="accent" />
        </div>

        <div className="row r-1-1">
          <PrototypeCard title="抢筹 TOP 10" icon={<FireOutlined />} meta="勾选后加入候选池" className="od-card-up">
            <table className="tbl">
              <thead><tr><th>选</th><th>#</th><th>代码</th><th>名称</th><th className="r">涨幅</th><th className="r">竞量比</th><th className="r">评分</th><th>意图</th></tr></thead>
              <tbody>
                {bullishRows.map((row, index) => (
                  <tr key={row.code}>
                    <td><input type="checkbox" aria-label={`选择 ${row.code}`} checked={selectedBullish.has(row.code)} onChange={() => toggleBullish(row.code)} /></td>
                    <td>{index + 1}</td>
                    <td className="code">{row.code}</td>
                    <td className="nm">{row.name}</td>
                    <td className="r up">+{row.gap ?? 0}%</td>
                    <td className="r mono">{row.vol}x</td>
                    <td className="r up">{row.score}</td>
                    <td><span className="tag t-up">{row.intent}</span></td>
                  </tr>
                ))}
                {bullishRows.length === 0 && <tr><td colSpan={8} className="prototype-panel-note">暂无抢筹数据，等待 signal/live 或 chain/candidates。</td></tr>}
              </tbody>
            </table>
            <div className="od-selection-bar">
              <span>已选 <b>{selectedBullish.size}</b></span>
              <button type="button" className="btn sm ghost" onClick={() => setSelectedBullish(new Set(bullishRows.map(row => row.code)))} disabled={bullishRows.length === 0}>全选可用</button>
              <button type="button" className="btn sm primary" onClick={handleAddBullishToPool} disabled={recordingPool || selectedBullish.size === 0} title={recordingPool ? '写入中…' : '把选中抢筹标的写入候选池'}>{recordingPool ? '写入中…' : '加入候选池'}</button>
            </div>
          </PrototypeCard>

          <PrototypeCard title="出货预警 TOP 10" icon={<SafetyCertificateOutlined />} meta="规避或反向观察" className="od-card-down">
            <table className="tbl">
              <thead><tr><th>选</th><th>#</th><th>代码</th><th>名称</th><th className="r">涨幅</th><th className="r">竞量比</th><th className="r">评分</th><th>意图</th></tr></thead>
              <tbody>
                {bearishRows.map((row, index) => (
                  <tr key={row.code}>
                    <td><input type="checkbox" aria-label={`选择 ${row.code}`} checked={selectedBearish.has(row.code)} onChange={() => toggleBearish(row.code)} /></td>
                    <td>{index + 1}</td>
                    <td className="code">{row.code}</td>
                    <td className="nm">{row.name}</td>
                    <td className="r down">{row.drop}%</td>
                    <td className="r mono">{row.vol}x</td>
                    <td className="r down">{row.score}</td>
                    <td><span className="tag t-down">{row.intent}</span></td>
                  </tr>
                ))}
                {bearishRows.length === 0 && <tr><td colSpan={8} className="prototype-panel-note">暂无出货预警。</td></tr>}
              </tbody>
            </table>
            <div className="od-selection-bar">
              <span>已选 <b>{selectedBearish.size}</b></span>
              <button type="button" className="btn sm ghost" onClick={() => setSelectedBearish(new Set(bearishRows.map(row => row.code)))} disabled={bearishRows.length === 0}>全选可用</button>
              <button type="button" className="btn sm down" onClick={handleAddBearishToWatch} disabled={watchingCode !== '' || selectedBearish.size === 0} title={watchingCode ? '加入中…' : '把选中出货标的加入自选观察'}>{watchingCode ? '加入中…' : '加入观察'}</button>
            </div>
          </PrototypeCard>
        </div>

        <div className="row r-16-8 mt14">
          <PrototypeCard title="竞价撮合价走势" icon={<LineChartOutlined />} meta="09:15-09:25 撮合价/匹配量">
            <div className="prototype-panel-note">暂无 09:15-09:25 分笔撮合序列接口；不展示模拟走势柱。</div>
          </PrototypeCard>

          <PrototypeCard title="四维评分" icon={<BarChartOutlined />} meta="价格方向 / 买卖压力 / 竞价强度 / 开盘延续">
            {firstBullish ? (
              <div className="od-score-bars">
                {[
                  ['综合评分', firstBullish.score],
                  ['竞价涨幅', Math.max(0, Math.min(100, Number(firstBullish.gap ?? 0) * 10))],
                  ['量能强度', Math.max(0, Math.min(100, Number(firstBullish.vol ?? 0) * 10))],
                ].map(([label, value]) => (
                  <div className="watch-sector-bar" key={label}>
                    <span>{label}</span>
                    <div><i style={{ width: `${value}%` }} /></div>
                    <b className="up">{value}</b>
                  </div>
                ))}
              </div>
            ) : (
              <div className="prototype-panel-note">暂无竞价评分标的。</div>
            )}
            <div className="od-stock-info">
              <span className="code">{firstBullish?.code || '-'}</span>
              <b>{firstBullish?.name || '暂无标的'}</b>
              <span className="tag t-up">{firstBullish?.intent || '等待信号'}</span>
            </div>
          </PrototypeCard>
        </div>

        <PrototypeCard title="一字定方向" icon={<BarChartOutlined />} meta="板块竞价热度 · 点击板块锁定并跳竞价选股" className="mt14">
          <div className="od-sector-grid">
            {sectorRows.map(row => (
              <button type="button" className={`od-sector-tile${selectedSector === row.name ? ' active' : ''}`} key={row.name} onClick={() => selectSector(row.name)} title={`锁定板块「${row.name}」并跳转竞价选股`}>
                <span>{row.name}</span>
                <b className="up">+{row.change}%</b>
                <small>{row.count} 只 · {row.lead}</small>
              </button>
            ))}
            {sectorRows.length === 0 && <div className="prototype-panel-note">暂无板块热度。</div>}
          </div>
        </PrototypeCard>

        <PrototypeCard title="全量竞价明细" icon={<BarChartOutlined />} meta={`共 ${bullishRows.length + bearishRows.length} 只 · 当前展示 ${Math.min(7, bullishRows.length + bearishRows.length)} 条`} className="mt14">
          <table className="tbl">
            <thead><tr><th>代码</th><th>名称</th><th>板块</th><th className="r">竞价涨跌</th><th className="r">竞量比</th><th className="r">评分</th><th>意图</th></tr></thead>
            <tbody>
              {[...bullishRows.slice(0, 5), ...bearishRows.slice(0, 2)].map(row => (
                <tr key={row.code}>
                  <td className="code">{row.code}</td>
                  <td className="nm">{row.name}</td>
                  <td>{row.industry || '风险观察'}</td>
                  <td className={`r ${'gap' in row ? 'up' : 'down'}`}>{'gap' in row ? `+${row.gap}%` : `${row.drop}%`}</td>
                  <td className="r mono">{row.vol}x</td>
                  <td className="r mono">{row.score}</td>
                  <td><span className={`tag ${'gap' in row ? 't-up' : 't-down'}`}>{row.intent}</span></td>
                </tr>
              ))}
              {bullishRows.length + bearishRows.length === 0 && <tr><td colSpan={7} className="prototype-panel-note">暂无竞价明细。</td></tr>}
            </tbody>
          </table>
        </PrototypeCard>
      </div>

      <aside className="od-auction-rail">
        <PrototypeCard title="板块共振详情" icon={<BarChartOutlined />}>
          {sectorRows.map(row => (
            <div className="od-resonance-row" key={row.name}>
              <div>
                <strong>{row.name}</strong>
                <span>{row.count}只 · 领涨: {row.lead}</span>
              </div>
              <b className="up">+{row.change}%</b>
              <button type="button" className="btn sm primary" onClick={() => selectSector(row.name)} title={`锁定板块「${row.name}」并跳转竞价选股`}>选股-&gt;</button>
            </div>
          ))}
          {sectorRows.length === 0 && <div className="prototype-panel-note">暂无板块共振详情。</div>}
        </PrototypeCard>

        <PrototypeCard title="板块强势标的" icon={<FireOutlined />}>
          {bullishRows.slice(0, 4).map(row => (
            <div className="li-row" key={row.code}>
              <span className="li-badge up">{row.score}</span>
              <div className="li-main"><div className="n">{row.name}</div><div className="s">{row.industry || '信号候选'} · +{row.gap ?? 0}% · {row.intent}</div></div>
            </div>
          ))}
          {bullishRows.length === 0 && <div className="prototype-panel-note">暂无强势标的。</div>}
        </PrototypeCard>

        <PrototypeCard title="候选池预览" icon={<FundOutlined />}>
          <div className="pool-count">{candidateRows.length}<span className="unit"> 只</span></div>
          <div className="chips mt14">
            {candidateRows.slice(0, 5).map((row, index) => <span className={index < 2 ? 'chip active' : 'chip'} key={row.code}>{row.code} {row.name}</span>)}
            {candidateRows.length === 0 && <span className="prototype-panel-note">暂无候选。</span>}
          </div>
          <button type="button" className="btn sm ghost mt14" onClick={() => navigate('/open-decision/candidates')} title="跳转候选池页签查看全部">查看全部候选池 -&gt;</button>
        </PrototypeCard>

        <PrototypeCard title="已锁定板块" icon={<CheckCircleOutlined />}>
          <div className="chips">
            {selectedSector
              ? <span className="chip active">{selectedSector}</span>
              : sectorRows.slice(0, 2).map(row => <span className="chip" key={row.name}>{row.name} ({row.count})</span>)}
            {!selectedSector && sectorRows.length === 0 && <span className="prototype-panel-note">暂无锁定板块。</span>}
          </div>
          <button type="button" className="btn primary mt14" style={{ width: '100%', justifyContent: 'center' }} onClick={() => navigate('/signals')} disabled={!selectedSector} title={selectedSector ? `带着已锁定板块「${selectedSector}」跳转信号扫描` : '先点上方板块锁定'}>锁定板块 -&gt; 信号扫描</button>
        </PrototypeCard>

        <PrototypeCard title="工作流引导" icon={<CheckCircleOutlined />}>
          {[
            ['done', '竞价意图全景 -> 判断抢筹/出货方向'],
            ['active', '锁定强势板块 -> 切换到竞价选股引擎'],
            ['todo', '勾选标的 -> 加入候选池 -> 信号扫描验证'],
          ].map(([state, text], index) => (
            <div className={`od-workflow-row ${state}`} key={text}>
              <span>{state === 'done' ? '✓' : index + 1}</span>
              <b>{text}</b>
            </div>
          ))}
        </PrototypeCard>
      </aside>
    </div>
  )
}
