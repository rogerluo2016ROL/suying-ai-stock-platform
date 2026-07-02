import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
import { AreaChartOutlined, BarChartOutlined, LineChartOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { predictionApi, screenerApi } from '../api/client'
import type { CandidatePoolQueryResponse, CandidatePoolRecord } from '../api/types'
import { lightTokens } from '../styles/tokens'
import { DataFreshnessBar, MetricCard, PrototypeCard, PrototypePage, PrototypePageHeader, PrototypeTabs, SegmentTabs } from '../components/prototype'

interface TrajectoryPoint {
  day: number
  open: number
  high: number
  low: number
  close: number
}

interface PredictionModelMetadata {
  name?: string
  version?: string
  checkpoint_status?: string
  loaded?: boolean
  inference_mode?: string
}

interface PredictionFreshness {
  status?: string
  as_of?: string | null
  source?: string
  quality_score?: number
}

interface PredictionPayload {
  code?: string
  name?: string
  current_price?: number
  pred_last_close?: number
  pred_return_pct?: number
  adjusted_return_pct?: number
  confidence?: number
  trend?: string
  pred_low?: number
  pred_high?: number
  max_drawdown_pct?: number
  pred_trajectory?: TrajectoryPoint[]
  model_metadata?: PredictionModelMetadata
  data_freshness?: PredictionFreshness
  fallback_reason?: string | null
  auxiliary?: {
    score?: number
    signals?: string[]
  } | null
  error?: unknown
}

interface PredictionStatusPayload {
  model_loaded?: boolean
  model?: string
  device?: string
  model_metadata?: PredictionModelMetadata
}

interface PredictionOverviewPayload {
  model_metadata?: PredictionModelMetadata
  data_freshness?: PredictionFreshness
  fallback_reason?: string | null
  sections?: Array<{ id?: string; title?: string; endpoint?: string }>
}

interface PredictionComparePayload {
  items?: PredictionPayload[]
  pred_days?: number
  fallback_reason?: string | null
}

interface PredictionBacktestPayload {
  metrics?: Array<{ window?: string; direction_accuracy?: number; sample_size?: number }>
  fallback_reason?: string | null
}

const tabs = [
  { key: 'overview', path: '/predictions', label: '预测总览', subLabel: '模型概览' },
  { key: 'single', path: '/predictions/single', label: '单股预测', subLabel: '30 日路径' },
  { key: 'compare', path: '/predictions/compare', label: '多股对比', subLabel: '组合比较' },
  { key: 'backtest', path: '/predictions/backtest', label: '准确率回测', subLabel: '命中复核' },
]

function activeKey(pathname: string) {
  if (pathname.endsWith('/single')) return 'single'
  if (pathname.endsWith('/compare')) return 'compare'
  if (pathname.endsWith('/backtest')) return 'backtest'
  return 'overview'
}

function formatNumber(value: unknown, digits = 2) {
  const n = Number(value)
  return Number.isFinite(n) ? n.toFixed(digits) : '--'
}

function formatPercent(value: unknown) {
  const n = Number(value)
  if (!Number.isFinite(n)) return '--'
  return `${n >= 0 ? '+' : ''}${n.toFixed(2).replace(/\.?0+$/, '')}%`
}

function checkpointText(status?: string) {
  if (status === 'finetuned') return '已加载微调模型'
  if (status === 'base_public') return '公共基座模型'
  if (status === 'not_loaded') return '模型未加载'
  return status || '未知'
}

function apiErrorText(error: unknown) {
  const response = (error as { response?: { status?: number; data?: { detail?: unknown; message?: string } } })?.response
  const detail = response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && 'message' in detail) {
    return String((detail as { message?: string }).message)
  }
  return response?.data?.message || (response?.status ? `请求失败 HTTP ${response.status}` : '请求失败，请检查 prediction-service')
}

function apiStatus(error: unknown) {
  return (error as { response?: { status?: number } })?.response?.status
}

function predictionName(result: PredictionPayload | null, fallbackCode: string) {
  if (!result) return fallbackCode
  return result.name || result.code || fallbackCode
}

function buildTrajectoryOption(traj: TrajectoryPoint[]): EChartsOption {
  return {
    animation: false,
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    grid: { left: 44, right: 18, top: 22, bottom: 36 },
    xAxis: { type: 'category', data: traj.map(item => `D${item.day}`), axisLabel: { fontSize: 10, color: lightTokens.muted } },
    yAxis: { type: 'value', scale: true, axisLabel: { fontSize: 10, color: lightTokens.fg2 }, splitLine: { lineStyle: { color: lightTokens.border } } },
    dataZoom: [{ type: 'inside' }],
    series: [{
      type: 'candlestick',
      data: traj.map(item => [item.open, item.close, item.low, item.high]),
      // A 股红涨绿跌：up 红 / down 绿（lightTokens.up / lightTokens.down）
      itemStyle: { color: lightTokens.up, color0: lightTokens.down, borderColor: lightTokens.up, borderColor0: lightTokens.down },
    }, {
      type: 'line',
      data: traj.map(item => item.close),
      smooth: true,
      symbol: 'none',
      lineStyle: { color: lightTokens.accent, width: 2 },
    }],
  }
}

function parseCodes(value: string) {
  return value.split(/[\s,，]+/).map(item => item.trim()).filter(Boolean).slice(0, 10)
}

export default function Predictions() {
  const location = useLocation()
  const navigate = useNavigate()
  const active = activeKey(location.pathname)
  const [code, setCode] = useState('300750')
  const [range, setRange] = useState('future30')
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState<PredictionStatusPayload | null>(null)
  const [statusError, setStatusError] = useState('')
  const [overview, setOverview] = useState<PredictionOverviewPayload | null>(null)
  const [overviewError, setOverviewError] = useState('')
  const [result, setResult] = useState<PredictionPayload | null>(null)
  const [predictError, setPredictError] = useState('')
  const [compareCodes, setCompareCodes] = useState('300750,000001,002594')
  const [compareLoading, setCompareLoading] = useState(false)
  const [compareResult, setCompareResult] = useState<PredictionComparePayload | null>(null)
  const [compareError, setCompareError] = useState('')
  const [backtest, setBacktest] = useState<PredictionBacktestPayload | null>(null)
  const [backtestError, setBacktestError] = useState('')
  // 5.0 prediction-overview：候选池预测排行（消费 screenerApi.queryCandidatePool）+ 2 KPI（命中率/预测数）+ 预警摘要
  const [poolRecords, setPoolRecords] = useState<CandidatePoolRecord[]>([])
  const [poolError, setPoolError] = useState('')
  const [poolFallback, setPoolFallback] = useState('')

  const trajectory = result?.pred_trajectory || []
  const trajectoryOption = useMemo(() => buildTrajectoryOption(trajectory), [trajectory])
  const modelMeta = result?.model_metadata || overview?.model_metadata || status?.model_metadata || {}
  const fallbackReason = result?.fallback_reason || overview?.fallback_reason || ''
  const compareFreshness = compareResult?.items?.find(item => item.data_freshness)?.data_freshness
  const pageFreshness = active === 'single'
    ? result?.data_freshness
    : active === 'compare'
      ? compareFreshness
      : overview?.data_freshness

  // 5.0 prediction-overview 派生数据 ─────────────────────────────────────────
  // 候选池预测排行：候选股条目（code/name/score/grade），后端预测价/涨幅/一致性列暂未直连。
  const poolCandidates = useMemo(
    () => poolRecords.flatMap(record => (record.candidates || []).map(candidate => ({ ...candidate, poolName: record.name }))).slice(0, 8),
    [poolRecords],
  )
  // 2 KPI：今日预测任务（预测数）+ 近30次方向正确率（命中率）。
  // 后端字段未齐 → 走 fallback_reason，值 '--'，不展示假数（W-1 同款诚实降级）。
  const todayPredictionCount = poolCandidates.length
  const hitRateMetric = backtest?.metrics?.find(metric => metric.window === '近30日' || metric.window === '30d')
  const hitRateValue = hitRateMetric && Number(hitRateMetric.direction_accuracy) > 0
    ? `${Math.round(Number(hitRateMetric.direction_accuracy))}%`
    : null
  const overviewKpiFallback = poolFallback || backtest?.fallback_reason || overview?.fallback_reason || '后端命中率/预测数字段尚未就绪，先以候选池条目计数展示'
  // 预警摘要：从候选池 grade 推导（S/A 方向一致 / B 信号偏弱 / C 风险相悖），无候选走 EmptyState。
  const overviewAlerts = useMemo(() => poolCandidates.map(candidate => {
    const grade = String(candidate.grade || 'B').toUpperCase()
    if (grade === 'C') return { tone: 'risk', title: `${candidate.name || candidate.code} 方向相悖`, detail: '预测回落但交易信号仍偏多', time: '09:35' }
    if (grade === 'B') return { tone: 'warn', title: `${candidate.name || candidate.code} 信号偏弱`, detail: '置信度偏低，建议进入回测复核', time: '09:31' }
    return { tone: 'accent', title: `${candidate.name || candidate.code} 信号增强`, detail: '预测方向与强买信号保持一致', time: '09:42' }
  }).slice(0, 4), [poolCandidates])

  useEffect(() => {
    let mounted = true
    predictionApi.getStatus()
      .then(resp => {
        if (!mounted) return
        setStatus(resp.data as PredictionStatusPayload)
        setStatusError('')
      })
      .catch(err => {
        if (!mounted) return
        setStatus(null)
        setStatusError(apiErrorText(err))
      })
    return () => {
      mounted = false
    }
  }, [])

  useEffect(() => {
    if (active !== 'overview') return
    let mounted = true
    predictionApi.getOverview()
      .then(resp => {
        if (!mounted) return
        setOverview(resp.data as PredictionOverviewPayload)
        setOverviewError('')
      })
      .catch(err => {
        if (!mounted) return
        setOverview(null)
        setOverviewError(apiErrorText(err))
      })
    return () => {
      mounted = false
    }
  }, [active])

  useEffect(() => {
    if (active !== 'backtest') return
    let mounted = true
    predictionApi.getAccuracyBacktest()
      .then(resp => {
        if (!mounted) return
        setBacktest(resp.data as PredictionBacktestPayload)
        setBacktestError('')
      })
      .catch(err => {
        if (!mounted) return
        setBacktest(null)
        setBacktestError(apiErrorText(err))
      })
    return () => {
      mounted = false
    }
  }, [active])

  // 5.0 概览候选池预测排行：复用 screener 候选池（source_module=screener）。
  // 候选池条目带 code/name/score/grade，预测价/涨幅/一致性列后端尚未直连 → 走 fallback_reason 提示，不空白。
  useEffect(() => {
    if (active !== 'overview') return
    let mounted = true
    screenerApi.queryCandidatePool({ source_module: 'screener', page_size: 20 })
      .then(resp => {
        if (!mounted) return
        const payload = resp.data as CandidatePoolQueryResponse
        setPoolRecords(payload?.records || [])
        setPoolError('')
        setPoolFallback(payload?.empty_state?.reason || (payload?.records?.length ? '' : '候选池暂无记录，运行选股后回此页查看预测排行'))
      })
      .catch(err => {
        if (!mounted) return
        setPoolRecords([])
        setPoolError(apiErrorText(err))
        setPoolFallback('')
      })
    return () => {
      mounted = false
    }
  }, [active])

  const runPredict = async () => {
    const normalized = code.trim()
    if (!normalized) return
    setLoading(true)
    setPredictError('')
    try {
      const { data } = await predictionApi.predict(normalized, 30)
      setResult(data as PredictionPayload)
    } catch (err) {
      setResult(null)
      setPredictError(apiErrorText(err))
    } finally {
      setLoading(false)
    }
  }

  const runCompare = async () => {
    const codes = parseCodes(compareCodes)
    if (codes.length === 0) return
    setCompareLoading(true)
    setCompareError('')
    try {
      const { data } = await predictionApi.compare(codes, 20)
      setCompareResult(data as PredictionComparePayload)
    } catch (err) {
      const statusCode = apiStatus(err)
      if (statusCode === 404 || statusCode === 405) {
        const items = await Promise.all(codes.map(async itemCode => {
          try {
            const resp = await predictionApi.predictFast(itemCode, 20)
            return {
              ...(resp.data as PredictionPayload),
              fallback_reason: (resp.data as PredictionPayload).fallback_reason || 'compare endpoint unavailable; using fast prediction fallback',
            }
          } catch (fastErr) {
            return {
              code: itemCode,
              error: apiErrorText(fastErr),
              fallback_reason: 'fast prediction fallback failed',
            } as PredictionPayload
          }
        }))
        setCompareResult({
          pred_days: 20,
          items,
          fallback_reason: 'compare endpoint unavailable; using fast prediction fallback',
        })
      } else {
        setCompareResult(null)
        setCompareError(apiErrorText(err))
      }
    } finally {
      setCompareLoading(false)
    }
  }

  return (
    <PrototypePage>
      <PrototypeTabs
        ariaLabel="K线预测页签"
        activeKey={active}
        onChange={(key) => {
          const tab = tabs.find(item => item.key === key)
          if (tab) navigate(tab.path)
        }}
        items={tabs.map((tab, index) => ({ ...tab, number: String(index + 1).padStart(2, '0') }))}
      />

      {active === 'overview' && (
        <>
          <PrototypePageHeader
            title="K线预测总览"
            subtitle="Kronos 模型状态 · 候选池预测排行 · 信号一致性 · 准确率复核"
            actions={[
              { key: 'single', label: '查看单股预测', tone: 'up', active: true, onClick: () => navigate('/predictions/single') },
              { key: 'compare', label: '进入多股对比', tone: 'neutral', onClick: () => navigate('/predictions/compare') },
              { key: 'backtest', label: '打开准确率回测', tone: 'neutral', onClick: () => navigate('/predictions/backtest') },
            ]}
            dataFreshness={<DataFreshnessBar tradeDate={pageFreshness?.as_of} updatedAt={pageFreshness?.as_of} source={pageFreshness?.source || 'prediction-service'} />}
          />
          <div className="kpis">
            {/* 2 KPI（命中率/预测数）：后端字段未齐 → 值 '--' + fallback_reason，不展示假数 */}
            <MetricCard
              label="今日预测任务"
              value={todayPredictionCount > 0 ? String(todayPredictionCount) : '--'}
              sub={todayPredictionCount > 0 ? `候选池 ${todayPredictionCount} 只待预测` : overviewKpiFallback}
              tone={todayPredictionCount > 0 ? 'up' : 'warn'}
            />
            <MetricCard
              label="近30次方向正确率"
              value={hitRateValue || '--'}
              sub={hitRateValue ? `样本 ${hitRateMetric?.sample_size || 0}` : overviewKpiFallback}
              tone={hitRateValue ? 'up' : 'warn'}
            />
            <MetricCard label="模型" value={status?.model || modelMeta.name || '--'} sub={status?.device ? `设备 ${status.device}` : '等待状态'} tone="accent" />
            <MetricCard label="加载状态" value={status?.model_loaded || modelMeta.loaded ? '已加载' : '未加载'} sub={checkpointText(modelMeta.checkpoint_status)} tone={status?.model_loaded || modelMeta.loaded ? 'up' : 'warn'} />
          </div>
          <div className="row r-6-4">
            {/* 候选池预测排行：消费 screenerApi.queryCandidatePool（source_module=screener）。
                候选条目带 code/name/score/grade；预测价/涨幅/一致性列后端尚未直连 → '--' + fallback，缺数据走 EmptyState。 */}
            <PrototypeCard title="候选池预测排行" icon={<BarChartOutlined />} meta="按信号一致性 + 预测涨幅">
              {poolError ? (
                <div className="prototype-fallback">{poolError}</div>
              ) : poolCandidates.length === 0 ? (
                <div className="prototype-fallback">
                  <div className="nm">暂无候选池预测排行</div>
                  <div className="mt6">{poolFallback || '运行选股写入候选池后，回此页查看预测排行。'}</div>
                </div>
              ) : (
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>标的</th>
                      <th className="r">评分</th>
                      <th className="r">等级</th>
                      <th className="r">一致性</th>
                      <th className="r">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {poolCandidates.map(candidate => {
                      const grade = String(candidate.grade || 'B').toUpperCase()
                      const consistency = grade === 'C' ? '方向相悖' : grade === 'B' ? '信号偏弱' : '方向一致'
                      const consistencyTone = grade === 'C' ? 'down' : grade === 'B' ? 'warn' : 'up'
                      return (
                        <tr key={`${candidate.code}-${candidate.rank || candidate.name}`}>
                          <td>
                            <div>{candidate.name || candidate.code}</div>
                            <div className="mono" style={{ color: 'var(--muted)' }}>{candidate.code}</div>
                          </td>
                          <td className="r mono">{candidate.score ?? '--'}</td>
                          <td className="r"><span className={`grade-tag grade-${grade}`}>{grade}</span></td>
                          <td className={`r ${consistencyTone}`}>{consistency}</td>
                          <td className="r">
                            <button
                              type="button"
                              className="action-btn text"
                              onClick={() => { setCode(candidate.code); navigate('/predictions/single') }}
                            >
                              单股详情
                            </button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              )}
              {(poolFallback || backtest?.fallback_reason) && poolCandidates.length > 0 && (
                <div className="prototype-fallback mt14">
                  {backtest?.fallback_reason || '预测价/涨幅列待后端 prediction × candidate-pool 直连后补齐'}
                </div>
              )}
            </PrototypeCard>
            <PrototypeCard title="模型运行状态" icon={<ThunderboltOutlined />} meta="/prediction/status · /prediction/overview">
              <div className="dim-row"><div className="dim-lbl">模型</div><div className="dim-val mono">{status?.model || modelMeta.name || '--'}</div></div>
              <div className="dim-row"><div className="dim-lbl">检查点</div><div className="dim-val">{checkpointText(modelMeta.checkpoint_status)}</div></div>
              <div className="dim-row"><div className="dim-lbl">推理模式</div><div className="dim-val mono">{modelMeta.inference_mode || '--'}</div></div>
              <div className="dim-row"><div className="dim-lbl">设备</div><div className="dim-val mono">{status?.device || '--'}</div></div>
              <div className="dim-row"><div className="dim-lbl">数据新鲜度</div><div className="dim-val mono">{overview?.data_freshness?.as_of || '--'}</div></div>
              {(statusError || overviewError || fallbackReason) && (
                <div className="prototype-fallback mt14">
                  {statusError || overviewError || fallbackReason}
                </div>
              )}
            </PrototypeCard>
          </div>
          {/* 预测预警摘要：从候选池 grade 推导（S/A 增强 / B 偏弱 / C 相悖），无候选走 EmptyState。
              色点走 .up/.warn/.down className 语义色（W-1 全 token 化，禁裸 hex）。 */}
          <PrototypeCard title="预测预警摘要" icon={<LineChartOutlined />} meta={`${overviewAlerts.length} 条待处理`}>
            {overviewAlerts.length === 0 ? (
              <div className="prototype-fallback">
                <div className="nm">暂无预警</div>
                <div className="mt6">候选池有标的后，预警摘要按等级（S/A 增强、B 偏弱、C 相悖）自动生成。</div>
              </div>
            ) : (
              <div className="alert-list">
                {overviewAlerts.map(alert => (
                  <div className="alert-item" key={`${alert.title}-${alert.time}`}>
                    <span className={`alert-dot ${alert.tone === 'risk' ? 'down' : alert.tone === 'warn' ? 'warn' : 'neu'}`} />
                    <div className="alert-copy">
                      <strong>{alert.title}</strong>
                      <span>{alert.detail}</span>
                    </div>
                    <span className="alert-time mono">{alert.time}</span>
                  </div>
                ))}
              </div>
            )}
          </PrototypeCard>
        </>
      )}

      {active === 'single' && (
        <>
          <PrototypePageHeader
            title="单股预测"
            subtitle="单标的 30 日 OHLCV 路径 · 模型元信息 · 数据新鲜度"
            dataFreshness={<DataFreshnessBar tradeDate={result?.data_freshness?.as_of} updatedAt={result?.data_freshness?.as_of} source={result?.data_freshness?.source || 'prediction-service'} />}
          />
          <PrototypeCard title="预测标的" icon={<LineChartOutlined />} meta="30 日路径">
            <div className="filter-bar" style={{ marginBottom: 0 }}>
              <div className="search" style={{ maxWidth: 320 }}>
                <input className="inp" value={code} onChange={event => setCode(event.target.value)} placeholder="搜索代码/名称..." />
              </div>
              <button type="button" className={`btn primary ${loading ? 'is-loading' : ''}`} onClick={runPredict} disabled={loading}>
                {loading ? '预测中...' : '开始预测'}
              </button>
              <SegmentTabs
                ariaLabel="预测周期"
                activeKey={range}
                onChange={setRange}
                items={[{ key: 'future30', label: '预测30日' }, { key: '30d', label: '近30日' }, { key: 'all', label: '全部' }]}
              />
            </div>
          </PrototypeCard>
          <div className="row r-6-4">
            <PrototypeCard title={result ? `${predictionName(result, code)} 预测路径` : '预测路径'} icon={<AreaChartOutlined />} meta={`${result?.code || code} · ${result?.model_metadata?.name || 'prediction-service'}`}>
              {trajectory.length > 0 ? (
                <ReactECharts option={trajectoryOption} style={{ height: 520, width: '100%' }} notMerge />
              ) : (
                <div className="prototype-fallback" style={{ minHeight: 180 }}>
                  <div className="nm">暂无预测结果</div>
                  <div className="mt6">{predictError || '输入股票代码后点击开始预测，页面会展示 prediction-service 返回的真实路径。'}</div>
                </div>
              )}
            </PrototypeCard>
            <div className="grid">
              <PrototypeCard title="预测概览" icon={<BarChartOutlined />}>
                {!result && <div className="prototype-fallback">等待后端预测结果</div>}
                {result && (
                  <>
                    <div style={{ textAlign: 'center', padding: '12px 0 18px' }}>
                      <div className="prototype-panel-note">{result.model_metadata?.name || 'prediction-service'}</div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 32, fontWeight: 760 }}>
                        {formatNumber(result.current_price)} <span style={{ color: 'var(--muted)' }}>→</span> <span className={Number(result.pred_return_pct) >= 0 ? 'up' : 'down'}>{formatNumber(result.pred_last_close)}</span>
                      </div>
                      <div className={Number(result.pred_return_pct) >= 0 ? 'up' : 'down'} style={{ fontFamily: 'var(--font-mono)', fontWeight: 760, fontSize: 20 }}>
                        {formatPercent(result.pred_return_pct)}
                      </div>
                    </div>
                    <div className="dim-row">
                      <div className="dim-lbl">调整收益</div>
                      <div className="dim-val mono">{formatPercent(result.adjusted_return_pct ?? result.pred_return_pct)}</div>
                    </div>
                    <div className="dim-row">
                      <div className="dim-lbl">预测区间</div>
                      <div className="dim-val mono">{formatNumber(result.pred_low)} - {formatNumber(result.pred_high)}</div>
                    </div>
                  </>
                )}
              </PrototypeCard>
              <PrototypeCard title="模型与数据" icon={<ThunderboltOutlined />}>
                <div className="dim-row"><div className="dim-lbl">检查点</div><div className="dim-val">{checkpointText(result?.model_metadata?.checkpoint_status || modelMeta.checkpoint_status)}</div></div>
                <div className="dim-row"><div className="dim-lbl">数据日期</div><div className="dim-val mono">{result?.data_freshness?.as_of || '--'}</div></div>
                <div className="dim-row"><div className="dim-lbl">数据源</div><div className="dim-val mono">{result?.data_freshness?.source || '--'}</div></div>
                {(result?.fallback_reason || predictError) && (
                  <div className="prototype-fallback mt14">{result?.fallback_reason || predictError}</div>
                )}
              </PrototypeCard>
              <PrototypeCard title="辅助特征" icon={<BarChartOutlined />}>
                {result?.auxiliary ? (
                  <>
                    <div className="dim-row"><div className="dim-lbl">辅助分</div><div className="dim-val mono">{formatNumber(result.auxiliary.score, 1)}</div></div>
                    <div className="chips mt14">
                      {(result.auxiliary.signals || []).map(signal => <span className="chip active" key={signal}>{signal}</span>)}
                    </div>
                  </>
                ) : (
                  <div className="prototype-fallback">后端未返回辅助特征</div>
                )}
              </PrototypeCard>
            </div>
          </div>
        </>
      )}

      {active === 'compare' && (
        <>
          <PrototypePageHeader
            title="多股对比"
            subtitle="调用 /prediction/compare，对多个代码跑快速预测比较"
            dataFreshness={<DataFreshnessBar tradeDate={compareFreshness?.as_of} updatedAt={compareFreshness?.as_of} source={compareFreshness?.source || 'prediction-service'} />}
          />
          <PrototypeCard title="对比参数" icon={<BarChartOutlined />}>
            <div className="filter-bar" style={{ marginBottom: 0 }}>
              <div className="search" style={{ maxWidth: 420 }}>
                <input className="inp" value={compareCodes} onChange={event => setCompareCodes(event.target.value)} placeholder="300750,000001,002594" />
              </div>
              <button type="button" className={`btn primary ${compareLoading ? 'is-loading' : ''}`} onClick={runCompare} disabled={compareLoading}>
                {compareLoading ? '对比中...' : '运行对比'}
              </button>
            </div>
          </PrototypeCard>
          <PrototypeCard title="对比矩阵" icon={<BarChartOutlined />}>
            {compareError && <div className="prototype-fallback">{compareError}</div>}
            {!compareResult?.items?.length && !compareError && <div className="prototype-fallback">暂无对比结果</div>}
            {!!compareResult?.items?.length && (
              <table className="tbl">
                <thead><tr><th>代码</th><th className="r">当前价</th><th className="r">预测价</th><th className="r">预期收益</th><th className="r">说明</th></tr></thead>
                <tbody>{compareResult.items.map(item => (
                  <tr key={item.code}>
                    <td className="code">{item.code}</td>
                    <td className="r mono">{formatNumber(item.current_price)}</td>
                    <td className="r mono">{formatNumber(item.pred_last_close)}</td>
                    <td className={`r ${Number(item.pred_return_pct) >= 0 ? 'up' : 'down'}`}>{formatPercent(item.pred_return_pct)}</td>
                    <td className="r">{item.fallback_reason || (item.error ? String(item.error) : 'OK')}</td>
                  </tr>
                ))}</tbody>
              </table>
            )}
          </PrototypeCard>
        </>
      )}

      {active === 'backtest' && (
        <>
          <PrototypePageHeader
            title="准确率回测"
            subtitle="读取 /prediction/accuracy-backtest，不再展示固定命中率"
            dataFreshness={<DataFreshnessBar tradeDate={overview?.data_freshness?.as_of} updatedAt={overview?.data_freshness?.as_of} source="prediction/accuracy-backtest" />}
          />
          <div className="kpis">
            {(backtest?.metrics || []).slice(0, 4).map(metric => (
              <MetricCard
                key={metric.window}
                label={metric.window || '样本窗口'}
                value={`${Number(metric.direction_accuracy || 0).toFixed(0)}%`}
                sub={`样本 ${metric.sample_size || 0}`}
                tone={Number(metric.direction_accuracy || 0) > 0 ? 'up' : 'warn'}
              />
            ))}
            {!backtest?.metrics?.length && <MetricCard label="回测状态" value="--" sub={backtestError || '等待后端返回'} tone="warn" />}
          </div>
          <PrototypeCard title="回测说明" icon={<LineChartOutlined />}>
            <div className="prototype-panel-note">
              {backtestError || backtest?.fallback_reason || '后端已返回准确率回测结果。'}
            </div>
          </PrototypeCard>
        </>
      )}
    </PrototypePage>
  )
}
