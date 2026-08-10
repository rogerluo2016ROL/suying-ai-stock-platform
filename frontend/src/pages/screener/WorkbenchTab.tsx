import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { message } from 'antd'
import { screenerApi, signalApi } from '../../api/client'
import type { ScreenerPick } from '../../api/types'
import {
  detailGroupsForModel,
  detailTitleForModel,
  evaluationForModel,
  factorLabel,
  formatMarketCap,
  formatScore,
  gradeClass,
  modelGroups,
  scoreTone,
  syncPlanForMode,
} from './helpers'
import type { RejectionSummaryItem, RunStage, ScreeningTraceStep, TradeDateResolver } from './types'

type WorkbenchTabProps = {
  selectedMode: string
  onSelectMode: (modeId: string) => void
  tradeDate: string
  onTradeDateChange: (value: string) => void
  onFreshnessSourceChange: (value: string) => void
  lastRunAt: string
  onLastRunAtChange: (value: string) => void
  latestDates: Record<string, string>
  resolveTradeDateForMode: TradeDateResolver
  picks: ScreenerPick[]
  onPicksChange: (picks: ScreenerPick[]) => void
  runMessage: string
  onRunMessageChange: (value: string) => void
}

export function WorkbenchTab({
  selectedMode,
  onSelectMode,
  tradeDate,
  onTradeDateChange,
  onFreshnessSourceChange,
  lastRunAt,
  onLastRunAtChange,
  latestDates,
  resolveTradeDateForMode,
  picks,
  onPicksChange,
  runMessage,
  onRunMessageChange,
}: WorkbenchTabProps) {
  const navigate = useNavigate()
  const [selectedGroup, setSelectedGroup] = useState(modelGroups[0].key)
  const [selectedCode, setSelectedCode] = useState('')
  const [selectedCodes, setSelectedCodes] = useState<string[]>([])
  const [hasRun, setHasRun] = useState(false)
  const [topN, setTopN] = useState(20)
  const [runStage, setRunStage] = useState<RunStage>('idle')
  const setRunMessage = onRunMessageChange
  const [noResultReason, setNoResultReason] = useState('')
  const [screeningTrace, setScreeningTrace] = useState<ScreeningTraceStep[]>([])
  const [rejectionSummary, setRejectionSummary] = useState<RejectionSummaryItem[]>([])
  const [expanded, setExpanded] = useState(false)
  const [loading, setLoading] = useState(false)
  const [recordingPool, setRecordingPool] = useState(false)
  const [watchingCode, setWatchingCode] = useState('')

  const visiblePicks = picks
  const selectedPick = visiblePicks.find(item => item.code === selectedCode) || visiblePicks[0]
  const selectedGroupConfig = modelGroups.find(item => item.key === selectedGroup) || modelGroups[0]
  const selectedModeConfig = selectedGroupConfig.modes.find(item => item.id === selectedMode) || selectedGroupConfig.modes[0]
  const detailGroups = detailGroupsForModel(selectedMode, selectedPick)
  const selectedCount = selectedCodes.length
  const canUseResults = visiblePicks.length > 0
  const selectedPicks = selectedCodes.length > 0
    ? visiblePicks.filter(item => selectedCodes.includes(item.code))
    : visiblePicks

  const emptyResultTitle = hasRun ? '当前模型返回 0 只' : '暂无选股结果'
  const emptyResultDetail = hasRun
    ? noResultReason || '请检查交易日、实时快照或切换到盘后龙头、趋势启动等日线模型后重新运行。'
    : '选择模型、日期和 Top 后点击运行选股。'

  const runScreener = async () => {
    setLoading(true)
    setRunStage('data')
    setNoResultReason('')
    setScreeningTrace([])
    setRejectionSummary([])
    const syncPlan = syncPlanForMode(selectedMode)
    setRunMessage(`正在同步 ${syncPlan.label} 数据：${syncPlan.tableKey}`)
    try {
      try {
        await signalApi.triggerSync(syncPlan.tableKey, syncPlan.days)
        setRunMessage(`${syncPlan.label} 数据同步完成，准备运行模型`)
      } catch {
        setRunMessage(`${syncPlan.label} 数据同步未完成，继续使用库内已有数据运行`)
      }
      setRunStage('model')
      setRunMessage(`正在运行 ${selectedModeConfig.name}，输出 Top ${topN}`)
      const runTradeDate = resolveTradeDateForMode(selectedMode)
      const response = await screenerApi.run(selectedMode, topN, runTradeDate)
      const nextPicks = response.data?.picks || []
      const actualTradeDate = response.data?.trade_date || response.data?.data_freshness?.as_of || tradeDate
      const nextNoResultReason = response.data?.no_result_reason || ''
      const nextScreeningTrace = response.data?.screening_trace || []
      const nextRejectionSummary = response.data?.rejection_summary || []
      setRunStage('output')
      setRunMessage(`模型完成，正在整理 ${nextPicks.length} 只候选股票`)
      setHasRun(true)
      onPicksChange(nextPicks)
      setNoResultReason(nextNoResultReason)
      setScreeningTrace(nextScreeningTrace)
      setRejectionSummary(nextRejectionSummary)
      setSelectedCodes(nextPicks[0]?.code ? [nextPicks[0].code] : [])
      setSelectedCode(nextPicks[0]?.code || '')
      if (actualTradeDate) onTradeDateChange(String(actualTradeDate).slice(0, 10))
      onFreshnessSourceChange(response.data?.data_freshness?.source || selectedMode)
      setRunStage('done')
      onLastRunAtChange(new Date().toISOString())
      setRunMessage(`已完成：${actualTradeDate || '后端未返回日期'} · ${selectedModeConfig.name} · 返回 ${nextPicks.length} 只`)
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : '运行失败，请检查后端服务和数据同步状态'
      setRunStage('error')
      setRunMessage(errorMessage)
      setHasRun(true)
      onPicksChange([])
      setNoResultReason('')
      setScreeningTrace([])
      setRejectionSummary([])
      setSelectedCodes([])
      setSelectedCode('')
      onLastRunAtChange(new Date().toISOString())
    } finally {
      setLoading(false)
    }
  }

  const selectPick = (pick: ScreenerPick) => {
    setSelectedCode(pick.code)
    setSelectedCodes([pick.code])
  }

  const selectAllPicks = () => {
    setSelectedCodes(visiblePicks.map(item => item.code).filter(Boolean))
    setSelectedCode(visiblePicks[0]?.code || '')
  }

  const clearSelectedPicks = () => {
    setSelectedCodes([])
    setSelectedCode('')
  }

  const exportCsv = () => {
    if (selectedPicks.length === 0) return
    const columns = ['代码', '名称', '行业', '评分', '等级', '入选理由']
    const escapeCell = (value: unknown) => `"${String(value ?? '').replace(/"/g, '""')}"`
    const rows = selectedPicks.map(pick => [
      pick.code,
      pick.name,
      pick.industry || pick.hard_tech?.track || '',
      formatScore(pick.score),
      pick.grade || '',
      pick.entry_reason || '',
    ])
    const csv = [columns, ...rows].map(row => row.map(escapeCell).join(',')).join('\n')
    const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `screener-${tradeDate}-${selectedMode}.csv`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  // 加入候选池：调 M0 recordCandidatePool 写入选中候选股（无显式选中时写全部 visiblePicks）。
  // scope 走 client 拦截器头（X-Tenant/Owner/Trade-Account），前端不传明文 tenant/owner/account。
  const addToCandidatePool = async () => {
    if (recordingPool || selectedPicks.length === 0) return
    const candidates = selectedPicks.map((pick, index) => ({
      code: pick.code,
      name: pick.name,
      score: Number.isFinite(Number(pick.score)) ? Number(pick.score) : undefined,
      grade: pick.grade,
      rank: index + 1,
    }))
    const payload = {
      source_module: 'screener',
      source_mode: selectedMode,
      name: `选股-${selectedMode}-${tradeDate || latestDates.daily_kline || '最新'}`,
      candidates,
      trade_date: resolveTradeDateForMode(selectedMode),
    }
    setRecordingPool(true)
    try {
      const response = await screenerApi.recordCandidatePool(payload)
      const poolId = response.data?.pool_id
      message.success(`已写入候选池${poolId ? `（${poolId}）` : ''}：${candidates.length} 只`)
      // 刷新侧栏计数（失败不阻断主链路）
      screenerApi.queryCandidatePool({ source_module: 'screener', source_mode: selectedMode }).catch(() => {})
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      message.error(detail || '候选池写入失败，请稍后重试')
    } finally {
      setRecordingPool(false)
    }
  }

  // 加入自选：调 watchlistApi.addWatchlist({code,name}) 写入选中候选股首只（或全部）。
  // 成功提示 + listWatchlist 刷新侧栏；fallback_reason 走 toast.error。
  const addToWatchlist = async () => {
    if (watchingCode || selectedPicks.length === 0) return
    const pick = selectedPicks[0]
    setWatchingCode(pick.code)
    try {
      const response = await screenerApi.addWatchlist({ code: pick.code, name: pick.name })
      const fallback = response.data?.fallback_reason
      if (response.data?.record) {
        message.success(`已加入自选：${pick.code} ${pick.name || ''}`)
      } else if (fallback) {
        message.error(fallback)
      } else {
        message.success(`已加入自选：${pick.code}`)
      }
      screenerApi.listWatchlist().catch(() => {})
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      message.error(detail || '加入自选失败，请稍后重试')
    } finally {
      setWatchingCode('')
    }
  }

  const stageState = (stage: 'data' | 'model' | 'output') => {
    const order = { idle: 0, data: 1, model: 2, output: 3, done: 4, error: 4 }
    const stageOrder = { data: 1, model: 2, output: 3 }
    if (runStage === 'error') return 'error'
    if (order[runStage] > stageOrder[stage]) return ' done'
    if (runStage === stage) return ' active'
    return ''
  }

  return (
    <>
      <section className="model-picker" aria-label="选股模型分类">
        <div className="model-tabs" role="tablist" aria-label="模型分类页签">
          {modelGroups.map(group => (
            <button
              type="button"
              role="tab"
              aria-selected={selectedGroup === group.key}
              className={`model-tab${selectedGroup === group.key ? ' active' : ''}`}
              key={group.key}
              onClick={() => {
                setSelectedGroup(group.key)
                onSelectMode(group.modes[0].id)
              }}
            >
              <span aria-hidden="true">{group.icon}</span>
              {group.label}
              <span className="tab-count">{group.count}</span>
            </button>
          ))}
        </div>
        <div className="model-panel active" role="tabpanel">
          <div className="model-panel-note">
            <span><b>{selectedGroupConfig.label}</b> {selectedGroupConfig.note}</span>
            <span>默认模型: {selectedGroupConfig.defaultModel}</span>
          </div>
          <div className="model-cards">
            {selectedGroupConfig.modes.map(mode => (
              <button
                type="button"
                key={mode.id}
                className={`model-card${selectedMode === mode.id ? ' active' : ''}`}
                onClick={() => onSelectMode(mode.id)}
              >
                <div className="mc-name">{mode.name}</div>
                <div className="mc-tags">
                  {mode.tags.map(tag => <span className="mc-tag" key={tag}>{tag}</span>)}
                </div>
              </button>
            ))}
          </div>
        </div>
      </section>

      <div className="param-bar">
        <span className="plabel">日期</span>
        <input
          type="date"
          className="param-input"
          aria-label="选股日期"
          value={tradeDate}
          onChange={event => {
            onTradeDateChange(event.target.value)
            onFreshnessSourceChange('手动选择')
          }}
        />
        <span className="psep" />
        <span className="plabel">Top</span>
        <select
          className="param-select"
          aria-label="Top 数量"
          value={topN}
          onChange={event => setTopN(Number(event.target.value))}
        >
          {[10, 20, 30, 50, 100].map(value => <option value={value} key={value}>{value}</option>)}
        </select>
        <span className="psep" />
        <span className="plabel">筛选</span>
        <button type="button" className="filter-btn active">全部</button>
        <button type="button" className="filter-btn">主板</button>
        <button type="button" className="filter-btn">创业板</button>
        <button type="button" className="filter-btn">科创板</button>
        <span className="psep" />
        <span className="plabel down">排除ST</span>
        <button type="button" className="run-btn" aria-label="开始选股 运行选股" onClick={runScreener} disabled={loading}>
          {loading ? '运行中...' : '▶ 运行选股'}
        </button>
      </div>

      <div className={`screener-run-status ${runStage === 'error' ? 'error' : ''}`} aria-live="polite">
        <div className={`run-step${stageState('data')}`}><span>1</span>数据更新</div>
        <div className={`run-step${stageState('model')}`}><span>2</span>模型选股</div>
        <div className={`run-step${stageState('output')}`}><span>3</span>输出股票</div>
        <div className="run-message">{runMessage}</div>
      </div>

      <div className="wb-main">
        <div className="wb-left">
          <div className="wb-table">
            <div className="wb-th">
              <span className="wb-rank">#</span>
              <span className="wb-cb">☑</span>
              <span className="wb-code">代码</span>
              <span className="wb-name">名称</span>
              <span className="wb-score">评分</span>
              <span className="wb-grade">等级</span>
              <span className="wb-industry">行业</span>
              <span className="wb-mcap">市值(亿)</span>
            </div>
            {visiblePicks.length === 0 && (
              <div className="wb-empty">
                <b>{emptyResultTitle}</b>
                <span>{emptyResultDetail}</span>
              </div>
            )}
            {visiblePicks.map((pick, index) => {
              const activePick = pick.code === selectedPick?.code
              const selected = selectedCodes.includes(pick.code)
              return (
                <button
                  type="button"
                  className={`wb-tr${activePick ? ' selected' : ''}`}
                  key={pick.code || index}
                  onClick={() => selectPick(pick)}
                >
                  <span className="wb-rank">{index + 1}</span>
                  <span className={`wb-cb ${selected ? 'neu' : ''}`}>{selected ? '☑' : '☐'}</span>
                  <span className={`wb-code ${activePick ? 'neu' : ''}`}>{pick.code}</span>
                  <span className="wb-name">{pick.name}</span>
                  <span className={`wb-score ${scoreTone(pick.score)}`}>{formatScore(pick.score)}</span>
                  <span className="wb-grade"><span className={`grade-tag ${gradeClass(pick.grade)}`}>{pick.grade || 'B'}</span></span>
                  <span className="wb-industry">{pick.industry || pick.hard_tech?.track || '综合'}</span>
                  <span className="wb-mcap">{formatMarketCap(pick.market_cap)}</span>
                </button>
              )
            })}
          </div>

          <div className="batch-actions">
            <button type="button" className="action-btn text" onClick={selectAllPicks} disabled={!canUseResults}>全选</button>
            <button type="button" className="action-btn text" onClick={clearSelectedPicks} disabled={selectedCount === 0}>清除</button>
            <span className="prototype-panel-note">已选</span>
            <span className="sel-cnt">{selectedCount}</span>
            <span className="prototype-panel-note">只</span>
            <button type="button" className="action-btn primary" onClick={addToCandidatePool} disabled={!canUseResults || recordingPool} title={recordingPool ? '正在写入候选池…' : '写入选中候选股到候选池'}>{recordingPool ? '写入中…' : '加入候选池 →'}</button>
            <button type="button" className="action-btn" onClick={addToWatchlist} disabled={!canUseResults || Boolean(watchingCode)} title={watchingCode ? '正在加入自选…' : '加入自选'}>{watchingCode ? '加入中…' : '加入自选'}</button>
            <button type="button" className="action-btn text" onClick={exportCsv} disabled={!canUseResults}>导出 CSV</button>
          </div>
        </div>

        <div className="wb-right">
          <div className="detail-card">
            <div className="detail-h">
              {detailTitleForModel(selectedMode)}
              {selectedPick && (
                <span className="stock-meta">
                  <span className="mono neu">{selectedPick.code}</span>
                  <span>标的 {selectedPick.name}</span>
                  <span className={`mono ${scoreTone(selectedPick.score)}`}>{formatScore(selectedPick.score)}</span>
                </span>
              )}
            </div>
            <div className="detail-b">
              {screeningTrace.length > 0 && (
                <div className="prototype-fallback">
                  <div className="nm">选债过程</div>
                  <div className="risk-list mt14">
                    {screeningTrace.map(item => (
                      <div
                        className={`risk-item ${item.status === 'ok' ? 'ok' : item.status === 'review' ? 'warn' : ''}`}
                        key={`${item.step}-${item.detail}`}
                      >
                        {item.step}: {item.detail}
                      </div>
                    ))}
                  </div>
                  {rejectionSummary.length > 0 && (
                    <div className="chips mt14">
                      {rejectionSummary.map(item => (
                        <span className="chip" key={item.reason}>{item.reason}：{item.count}</span>
                      ))}
                    </div>
                  )}
                </div>
              )}
              {!selectedPick && (
                <div className="prototype-fallback">
                  <div className="nm">{hasRun ? '当日无模型输出' : '等待模型输出'}</div>
                  <div className="mt6">{hasRun ? emptyResultDetail : '当前没有可展示的股票明细，运行成功后这里会展示首只候选的指标、风险和模型评价。'}</div>
                </div>
              )}
              {selectedPick && (
                <>
                <div className="lineage-chips">
                  <span className="lineage-chip safe">赛道 <b>{selectedPick?.hard_tech?.track || selectedPick?.industry || '综合'}赛道</b></span>
                  <span className="lineage-chip accent">层级 <b>{selectedPick?.hard_tech?.tier || selectedPick?.grade || 'watch'}</b></span>
                </div>
                {detailGroups.map(group => (
                  <div className="ind-group" key={group.name}>
                    <div className="ind-group-label">{group.name}</div>
                    {group.items.map(([label, width, color, value]) => (
                      <div className="ind-bar" key={String(label)}>
                        <span className="ind-bar-label">{label}</span>
                        <div className="ind-bar-track"><div className="ind-bar-fill" style={{ width: `${width}%`, background: String(color) }} /></div>
                        <span className="ind-bar-val" style={{ color: String(color) }}>{value}</span>
                      </div>
                    ))}
                  </div>
                ))}

                <div className="eval-box">
                  <div className="ev-title">模型评价</div>
                  {evaluationForModel(selectedMode, selectedPick)}
                </div>
                <div className="risk-list">
                  <div className="risk-item ok">ST风险: 通过</div>
                  <div className="risk-item ok">涨幅过热: 通过</div>
                  {(selectedPick?.risk_flags || []).map(flag => <div className="risk-item warn" key={flag}>需复核: {flag}</div>)}
                </div>
                <div className="detail-actions">
                  <button type="button" className="action-btn primary" onClick={addToCandidatePool} disabled={recordingPool} title={recordingPool ? '正在写入候选池…' : '写入选中候选股到候选池'}>{recordingPool ? '写入中…' : '加入候选池'}</button>
                  <button
                    type="button"
                    className="action-btn"
                    onClick={() => navigate(`/backtest?code=${encodeURIComponent(selectedPick.code)}&mode=${encodeURIComponent(selectedMode)}`)}
                  >
                    触发回测
                  </button>
                  <button
                    type="button"
                    className="action-btn"
                    onClick={() => navigate(`/diagnosis?code=${encodeURIComponent(selectedPick.code)}`)}
                  >
                    查看诊断
                  </button>
                </div>
                <button type="button" className="action-btn text screener-expand-btn" onClick={() => setExpanded(value => !value)}>
                  {expanded ? '收起四轴解释' : '展开四轴解释'}
                </button>
                {expanded && selectedPick && (
                  <div className="prototype-fallback mt14">
                    <div className="nm">{selectedPick.entry_reason}</div>
                    <div className="chips mt14">
                      {(selectedPick.risk_flags || []).map(flag => <span className="chip" key={flag}>{flag}</span>)}
                      {(selectedPick.power_flags || []).map(flag => <span className="chip active" key={flag}>{flag}</span>)}
                      {Object.entries(selectedPick.factor_breakdown || {}).map(([key, value]) => (
                        <span className="chip active" key={key}>
                          {factorLabel(key)} {Number(value).toFixed(1)}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="footer-bar">
        <span>智能选股 · 选股工作台 | {lastRunAt ? `最近运行 ${new Date(lastRunAt).toLocaleTimeString('zh-CN', { hour12: false })}` : '等待运行'}</span>
        <span className="sep" />
        <span>模型: {selectedModeConfig.name}（{selectedMode}） | 结果: {visiblePicks.length}只</span>
        <span className="sep" />
        <span>数据来源: screener-service + Kronos 模型引擎</span>
      </div>
    </>
  )
}
