import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { BarChartOutlined, HistoryOutlined, SafetyCertificateOutlined, ThunderboltOutlined } from '@ant-design/icons'
import {
  DataDomainBadge,
  EmptyState,
  LineageChips,
  MetricCard,
  PrototypeCard,
  PrototypePage,
  PrototypePageHeader,
  PrototypeTabs,
  RiskBanner,
  SideRail,
} from '../components/prototype'
import { signalApi } from '../api/client'

interface SignalRow {
  code: string
  name?: string
  signal?: string
  level?: string
  strength?: number
  confidence?: number
  score?: number
  reason?: string
  risk?: string
}

interface SignalHistoryRow extends SignalRow {
  date?: string
  hit?: boolean
  return_pct?: number
}

interface RiskScanResult {
  code?: string
  risk_score?: number
  verdict?: string
  blockers?: string[]
  risk_alerts?: string[]
  recommendation?: string
}

const tabs = [
  { key: 'detail', path: '/signals', label: '信号详情', subLabel: '当前触发' },
  { key: 'overview', path: '/signals/overview', label: '信号总览', subLabel: '强弱分布' },
  { key: 'history', path: '/signals/history', label: '信号历史', subLabel: '命中回看' },
  { key: 'risk', path: '/signals/risk', label: '风险扫描', subLabel: '交易前置' },
]

const fallbackSignals: SignalRow[] = [
  { code: '300750', name: '宁德时代', signal: '买入', level: 'buy', strength: 82, confidence: 78, reason: '竞价强 + 资金共振', risk: '低' },
  { code: '688981', name: '中芯国际', signal: '强买', level: 'strong_buy', strength: 78, confidence: 74, reason: '半导体共振', risk: '中' },
  { code: '600519', name: '贵州茅台', signal: '观察', level: 'hold', strength: 63, confidence: 66, reason: '资金回补但量能不足', risk: '低' },
]

const fallbackHistory: SignalHistoryRow[] = [
  { code: '300750', name: '宁德时代', signal: '买入', date: '2026-06-25', hit: true, return_pct: 8.2, strength: 82 },
  { code: '688981', name: '中芯国际', signal: '强买', date: '2026-06-24', hit: true, return_pct: 5.8, strength: 78 },
  { code: '002594', name: '比亚迪', signal: '卖出', date: '2026-06-21', hit: false, return_pct: -2.1, strength: 68 },
]

function activeKey(pathname: string) {
  if (pathname.endsWith('/overview')) return 'overview'
  if (pathname.endsWith('/history')) return 'history'
  if (pathname.endsWith('/risk')) return 'risk'
  return 'detail'
}

function signalLabel(row: SignalRow) {
  if (row.signal) return row.signal
  if (row.level === 'strong_buy') return '强买'
  if (row.level === 'buy') return '买入'
  if (row.level === 'sell') return '卖出'
  if (row.level === 'strong_sell') return '强卖'
  return '观察'
}

function signalStrength(row: SignalRow) {
  return row.strength ?? row.score ?? row.confidence ?? 0
}

function riskStatus(result?: RiskScanResult): 'pass' | 'warn' | 'reject' | 'review' {
  if (!result) return 'review'
  if (result.verdict === 'reject') return 'reject'
  if (result.verdict === 'pass') return 'pass'
  if ((result.risk_score ?? 0) >= 70) return 'reject'
  if ((result.risk_score ?? 0) >= 35 || result.verdict === 'warn') return 'warn'
  return 'pass'
}

function formatReturn(value?: number) {
  if (typeof value !== 'number') return '--'
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`
}

export default function Signals() {
  const location = useLocation()
  const navigate = useNavigate()
  const active = activeKey(location.pathname)
  const activeTab = useMemo(() => tabs.find(tab => tab.key === active) ?? tabs[0], [active])
  const [signals, setSignals] = useState<SignalRow[]>(fallbackSignals)
  const [history, setHistory] = useState<SignalHistoryRow[]>(fallbackHistory)
  const [riskResult, setRiskResult] = useState<RiskScanResult | undefined>()
  const [selectedCode, setSelectedCode] = useState(fallbackSignals[0].code)

  useEffect(() => {
    signalApi.getLive('intra')
      .then(response => {
        const data = response.data as unknown as { signals?: SignalRow[], items?: SignalRow[] }
        const nextSignals = data.signals || data.items || []
        if (nextSignals.length > 0) {
          setSignals(nextSignals)
          setSelectedCode(nextSignals[0].code)
        }
      })
      .catch(() => undefined)
  }, [])

  useEffect(() => {
    if (active !== 'history') return
    signalApi.getHistory()
      .then(response => {
        const data = response.data as unknown as { history?: SignalHistoryRow[], signals?: SignalHistoryRow[], items?: SignalHistoryRow[] }
        const nextHistory = data.history || data.signals || data.items || []
        if (nextHistory.length > 0) setHistory(nextHistory)
      })
      .catch(() => undefined)
  }, [active])

  useEffect(() => {
    if (active !== 'risk') return
    signalApi.analyzeCode(selectedCode)
      .then(response => setRiskResult(response.data as unknown as RiskScanResult))
      .catch(() => setRiskResult(undefined))
  }, [active, selectedCode])

  const selectedSignal = signals.find(item => item.code === selectedCode) ?? signals[0] ?? fallbackSignals[0]
  const riskItems = riskResult?.blockers || riskResult?.risk_alerts || []
  const strongCount = signals.filter(item => ['强买', '买入'].includes(signalLabel(item))).length
  const warnCount = signals.filter(item => item.risk && item.risk !== '低').length
  const hitCount = history.filter(item => item.hit).length
  const avgHitReturn = history.length > 0
    ? history.reduce((sum, item) => sum + (item.return_pct || 0), 0) / history.length
    : 0

  return (
    <PrototypePage>
      <PrototypeTabs
        ariaLabel="交易信号页签"
        activeKey={active}
        onChange={(key) => {
          const tab = tabs.find(item => item.key === key)
          if (tab) navigate(tab.path)
        }}
        items={tabs.map((tab, index) => ({ ...tab, number: String(index + 1).padStart(2, '0') }))}
      />
      <PrototypePageHeader
        title={`交易信号 - ${activeTab.label}`}
        subtitle="实时触发 · 证据链 · 历史命中 · 交易前风控"
        actions={[
          { key: 'public', label: '公共信号源' },
          { key: 'account', label: '账户订阅', active: true, tone: 'neutral' },
          { key: 'risk', label: warnCount > 0 ? `${warnCount} 个需复核` : '风险通过', tone: warnCount > 0 ? 'warn' : 'up' },
        ]}
      />

      <div className="kpis">
        <MetricCard label="今日信号" value={String(signals.length)} sub="signal-service" tone="accent" />
        <MetricCard label="可入候选" value={String(strongCount)} sub="强买 / 买入" tone="up" />
        <MetricCard label="需复核" value={String(warnCount)} sub="账户风险过滤" tone="warn" />
        <MetricCard label="历史均值" value={formatReturn(avgHitReturn)} sub={`命中 ${hitCount}/${history.length}`} tone={avgHitReturn >= 0 ? 'down' : 'up'} />
      </div>

      {active === 'detail' && (
        <div className="row r-6-4">
          <PrototypeCard title="实时触发队列" icon={<ThunderboltOutlined />} meta="Signal">
            <div className="filter-bar">
              <div className="chips">
                <span className="chip active">全部 {signals.length}</span>
                <span className="chip">强买 {signals.filter(item => signalLabel(item) === '强买').length}</span>
                <span className="chip">买入 {signals.filter(item => signalLabel(item) === '买入').length}</span>
              </div>
              <button type="button" className="btn ghost" onClick={() => navigate('/signals/risk')}>
                风险扫描
              </button>
            </div>
            <table className="tbl">
              <thead>
                <tr>
                  <th>代码</th>
                  <th>名称</th>
                  <th>触发信号</th>
                  <th className="r">强度</th>
                  <th className="r">风险</th>
                  <th>证据</th>
                </tr>
              </thead>
              <tbody>
                {signals.map(row => (
                  <tr
                    key={row.code}
                    className={selectedCode === row.code ? 'sel' : ''}
                    onClick={() => setSelectedCode(row.code)}
                  >
                    <td className="code">{row.code}</td>
                    <td className="nm">{row.name || '--'}</td>
                    <td><span className="tag t-neu">{signalLabel(row)}</span></td>
                    <td className="r mono">{signalStrength(row)}</td>
                    <td className={`r ${row.risk === '高' ? 'down' : row.risk === '中' ? 'warn' : 'up'}`}>{row.risk || '低'}</td>
                    <td>{row.reason || '技术面 + 资金面共振'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </PrototypeCard>

          <SideRail title="候选联动" meta="Candidate / Plan">
            <DataDomainBadge domain="account" label="账户订阅信号" />
            <LineageChips
              items={[
                { label: 'DecisionContext', value: `DC-${selectedSignal.code}` },
                { label: 'Candidate', value: `CAND-${selectedSignal.code}`, tone: 'accent' },
                { label: 'RiskVerdict', value: '待预检', tone: 'warn' },
              ]}
            />
            <RiskBanner status="review" title="进入候选前预检" detail={`${selectedSignal.name || selectedSignal.code} 的信号需通过账户资金、仓位和黑名单规则。`} />
            <EmptyState title="等待入池动作" detail="确认后写入账户私有候选池，并保留信号证据链。" actionLabel="加入候选池" />
          </SideRail>
        </div>
      )}

      {active === 'overview' && (
        <div className="row r-6-4">
          <PrototypeCard title="信号强弱分布" icon={<BarChartOutlined />} meta="Signal Overview">
            {[
              ['强买', signals.filter(item => signalLabel(item) === '强买').length, 'var(--down)'],
              ['买入', signals.filter(item => signalLabel(item) === '买入').length, 'var(--accent)'],
              ['观察', signals.filter(item => signalLabel(item) === '观察').length, 'var(--fg-3)'],
              ['卖出', signals.filter(item => signalLabel(item).includes('卖')).length, 'var(--up)'],
            ].map(([label, value, color]) => (
              <div className="dim-row" key={String(label)}>
                <div className="dim-lbl">{label}</div>
                <div className="dim-bar-wrap">
                  <div className="dim-bar" style={{ width: `${Math.max(8, Number(value) * 28)}%`, background: String(color) }} />
                </div>
                <div className="dim-val">{value}</div>
              </div>
            ))}
          </PrototypeCard>
          <SideRail title="数据隔离" meta="tenant/user">
            <DataDomainBadge domain="tenant" label="租户公共信号" />
            <DataDomainBadge domain="account" label="账户订阅结果" />
            <RiskBanner status="pass" title="订阅边界清晰" detail="公共信号只读复用，账户候选、方案和交易记录独立保存。" />
          </SideRail>
        </div>
      )}

      {active === 'history' && (
        <div className="row r-6-4">
          <PrototypeCard title="命中率回看" icon={<HistoryOutlined />} meta="Signal History">
            <table className="tbl">
              <thead>
                <tr>
                  <th>日期</th>
                  <th>代码</th>
                  <th>名称</th>
                  <th>信号</th>
                  <th className="r">结果</th>
                  <th className="r">收益</th>
                </tr>
              </thead>
              <tbody>
                {history.map(row => (
                  <tr key={`${row.code}-${row.date}`}>
                    <td className="mono">{row.date || '--'}</td>
                    <td className="code">{row.code}</td>
                    <td className="nm">{row.name || '--'}</td>
                    <td>{signalLabel(row)}</td>
                    <td className={`r ${row.hit ? 'up' : 'down'}`}>{row.hit ? '命中' : '未命中'}</td>
                    <td className={`r mono ${(row.return_pct || 0) >= 0 ? 'up' : 'down'}`}>{formatReturn(row.return_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </PrototypeCard>
          <SideRail title="回测复盘" meta="Backtest">
            <LineageChips
              items={[
                { label: '样本', value: history.length },
                { label: '命中', value: `${hitCount}/${history.length}`, tone: 'accent' },
                { label: '均值', value: formatReturn(avgHitReturn), tone: avgHitReturn >= 0 ? 'safe' : 'danger' },
              ]}
            />
            <RiskBanner status="review" title="信号版本已归档" detail="历史命中按 model_version/run_id 分层复核，避免新模型覆盖旧信号口径。" />
          </SideRail>
        </div>
      )}

      {active === 'risk' && (
        <div className="row r-6-4">
          <PrototypeCard title="RiskVerdict 预检" icon={<SafetyCertificateOutlined />} meta="Risk">
            <div className="op-hint">
              <div className={`pos ${riskStatus(riskResult) === 'reject' ? 'down' : riskStatus(riskResult) === 'warn' ? 'warn' : 'up'}`}>
                {riskResult?.risk_score ?? 28}
              </div>
              <div>
                <div className="op-title">{selectedSignal.name || selectedSignal.code} · {signalLabel(selectedSignal)}</div>
                <div className="op-desc">账户仓位、黑名单、流动性、涨跌停距离和模拟/实盘模式预检。</div>
              </div>
            </div>
            <div className="grid mt14">
              {[
                ['仓位闸门', '通过', '单票目标仓位低于上限'],
                ['流动性', riskStatus(riskResult) === 'reject' ? '拒绝' : '通过', '成交额满足最小阈值'],
                ['审计留痕', '通过', '预检结果随订单草稿保存'],
              ].map(([name, result, detail]) => (
                <div className="li-row" key={name}>
                  <span className={`li-badge ${result === '拒绝' ? 'up' : 'neu'}`}>{result === '拒绝' ? '!' : '✓'}</span>
                  <div className="li-main"><div className="n">{name}</div><div className="s">{detail}</div></div>
                </div>
              ))}
            </div>
            {riskItems.length > 0 && (
              <div className="prototype-fallback mt14">
                <strong>阻断项</strong>
                <div className="chips mt14">
                  {riskItems.map(item => <span className="chip" key={item}>{item}</span>)}
                </div>
              </div>
            )}
          </PrototypeCard>
          <SideRail title="风控结论" meta="Order Gate">
            <DataDomainBadge domain="account" label="账户级风控" />
            <RiskBanner
              status={riskStatus(riskResult)}
              title={riskStatus(riskResult) === 'pass' ? '可进入下单面板' : '需要人工复核'}
              detail={riskResult?.recommendation || '预检结果会随 Order 草稿一起写入 RiskVerdict。'}
            />
            <LineageChips
              items={[
                { label: 'Signal', value: selectedSignal.code },
                { label: 'Plan', value: '待选择', tone: 'warn' },
                { label: 'Order', value: '未生成', tone: 'warn' },
              ]}
            />
          </SideRail>
        </div>
      )}
    </PrototypePage>
  )
}
