import { useMemo } from 'react'
import {
  BarChartOutlined,
  LineChartOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { MetricCard, PrototypeCard } from '../../components/prototype'
import { buildAiSentimentReasons, currentTimeText, overnightNews } from './helpers'
import type { CandidateRow, SectorRow, SignalRow } from './types'

export default function OverviewTab({
  loading,
  error,
  signalRows,
  candidateRows,
  sectorRows,
}: {
  loading: boolean
  error: string
  signalRows: SignalRow[]
  candidateRows: CandidateRow[]
  sectorRows: SectorRow[]
}) {
  const avgScore = signalRows.length ? Math.round(signalRows.reduce((sum, row) => sum + row.score, 0) / signalRows.length) : 0
  const strongSignals = signalRows.filter(row => row.score >= 70 && row.risk === '通过').length
  const nowText = currentTimeText()
  const aiReasons = useMemo(
    () => buildAiSentimentReasons({ avgScore, strongSignals, candidateCount: candidateRows.length, sectors: sectorRows }),
    [avgScore, strongSignals, candidateRows.length, sectorRows],
  )
  return (
    <>
      <section className="od-countdown card">
        <div>
          <div className="od-time mono">{nowText}</div>
          <strong>当前时间</strong>
          <span>竞价数据以 dashboard/auction 与 signal/live 返回为准</span>
        </div>
        <div className="prototype-panel-note">竞价开始后自动切换到竞价分析</div>
      </section>

      <div className="kpis od-kpis-5">
        <MetricCard label="情绪指数" value={avgScore ? String(avgScore) : '-'} sub="signal/live" tone="warn" />
        <MetricCard label="熔断器" value={error ? '复核' : '正常'} sub={error || '接口在线'} tone={error ? 'warn' : 'down'} />
        <MetricCard label="隔夜公告" value="-" sub="暂无实时接口" tone="up" />
        <MetricCard label="候选池" value={`${candidateRows.length}只`} sub={`强信号 ${strongSignals} 只`} tone="accent" />
        <MetricCard label="数据状态" value={loading ? '加载中' : '已刷新'} sub="signal + trade + chain" tone="down" />
      </div>

      <div className="row r-6-4">
        <div className="grid">
          <PrototypeCard title="隔夜新闻" icon={<LineChartOutlined />} meta="最近 12 小时">
            <div className="od-news-list">
              {overnightNews.map(item => (
                <div className="od-news-row" key={item.title}>
                  <span className={`od-news-tag ${item.tone}`}>{item.type}</span>
                  <div className="od-news-main">
                    <strong>{item.title}</strong>
                    <span>{item.impact}</span>
                  </div>
                  <time className="mono">{item.time}</time>
                </div>
              ))}
              {overnightNews.length === 0 && <div className="prototype-panel-note">暂无隔夜新闻实时接口；不展示演示新闻。</div>}
            </div>
            <div className="od-news-summary">
              <div>
                <span>摘要</span>
                <strong>等待新闻/舆情接口返回后生成摘要</strong>
              </div>
              <button type="button" className="btn sm ghost" disabled>暂无原始结果</button>
            </div>
          </PrototypeCard>

          <PrototypeCard title="昨日复盘" icon={<LineChartOutlined />} meta="回看强势线索">
            <div className="prototype-panel-note">暂无昨日复盘实时接口；不展示固定复盘样例。</div>
          </PrototypeCard>

          <PrototypeCard title="候选池预加载" icon={<ThunderboltOutlined />} meta="开盘前预热">
            <div className="chips">
              {candidateRows.map(row => <span className="chip active" key={row.code}>{row.name} {row.score}</span>)}
              {candidateRows.length === 0 && <span className="prototype-panel-note">暂无候选池数据，等待 chain/candidates 返回。</span>}
            </div>
            <div className="prototype-panel-note mt14">来自产业链候选、实时信号和风控判定，开盘后进入去重与风控。</div>
          </PrototypeCard>
        </div>

        <div className="grid">
          <PrototypeCard title="今日情绪 + 风控" icon={<SafetyCertificateOutlined />} meta="开盘前">
            <div className="op-hint">
              <div className="pos warn">{avgScore ? `${Math.min(9, Math.max(1, Math.round(avgScore / 10)))}成` : '-'}</div>
              <div>
                <div className="op-title warn">{strongSignals ? '信号已触发，需逐条确认' : '等待实时信号'}</div>
                <div className="op-desc">优先选择信号强、风控通过、候选来源清晰的标的。</div>
              </div>
            </div>
            <div className="ai-sentiment-card mt14">
              <div className="ai-title"><span>AI 开盘解读</span><em>基于 signal/live + 候选池</em></div>
              <div className="ai-reason-grid">
                {aiReasons.map(reason => (
                  <div key={reason.title}>
                    <strong>{reason.title}{reason.fallback ? ' · 待补齐' : ''}</strong>
                    <span>{reason.detail}</span>
                  </div>
                ))}
              </div>
              <div className="risk-banner warn"><strong>风险提醒</strong><span>本解读只使用接口返回字段；缺失的资金/竞价/历史归因不会用演示数据补齐。</span></div>
            </div>
          </PrototypeCard>

          <PrototypeCard title="实时板块共振" icon={<BarChartOutlined />} meta="按接口聚合">
            {sectorRows.slice(0, 4).map(row => (
              <div className="watch-sector-bar" key={row.name}>
                <span>{row.name}</span>
                <div><i style={{ width: `${row.width}%` }} /></div>
                <b className="up">+{row.change}%</b>
              </div>
            ))}
            {sectorRows.length === 0 && <div className="prototype-panel-note">暂无板块共振数据。</div>}
          </PrototypeCard>
        </div>
      </div>

      <div className="footer-bar">
        <span>开盘决策 · 决策总览 | 当前 {nowText}</span>
        <span className="sep" />
        <span>隔夜新闻: stock_news + announcements + cctv_news</span>
        <span className="sep" />
        <span>候选池: CandidatePoolManager (screening_snapshots + watchlist)</span>
      </div>
    </>
  )
}
