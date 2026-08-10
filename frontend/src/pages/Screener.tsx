import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  DataFreshnessBar,
  PrototypePage,
  PrototypePageHeader,
  PrototypeTabs,
} from '../components/prototype'
import { backtestApi, screenerApi } from '../api/client'
import type { ScreenerPick } from '../api/types'
import { toFactorEvidenceView, type FactorEvidenceView } from './screener/factorEvidence'
import {
  activeKey,
  buildIndustryRows,
  createTradeDateResolver,
  modelGroups,
  normalizeLatestDates,
  syncPlanForMode,
  tabs,
  todayDateInputValue,
} from './screener/helpers'
import { FactorsTab } from './screener/FactorsTab'
import { ModelsTab } from './screener/ModelsTab'
import { useModelCompare } from './screener/useModelCompare'
import { WorkbenchTab } from './screener/WorkbenchTab'

export default function Screener() {
  const location = useLocation()
  const navigate = useNavigate()
  const active = activeKey(location.pathname)
  const [selectedMode, setSelectedMode] = useState(modelGroups[0].modes[0].id)
  const [picks, setPicks] = useState<ScreenerPick[]>([])
  const [tradeDate, setTradeDate] = useState(todayDateInputValue)
  const [runMessage, setRunMessage] = useState('正在读取最新可用交易日')
  const [lastRunAt, setLastRunAt] = useState('')
  const [freshnessSource, setFreshnessSource] = useState('screener-service')
  const [latestDates, setLatestDates] = useState<Record<string, string>>({})
  const [factorEvidenceView, setFactorEvidenceView] = useState<FactorEvidenceView | null>(null)
  const [factorEvidenceLoading, setFactorEvidenceLoading] = useState(false)

  const resolveTradeDateForMode = useMemo(
    () => createTradeDateResolver(latestDates, tradeDate),
    [latestDates, tradeDate],
  )

  const { modelCompareRows, modelComparePicks, modelCompareLoading, modelCompareMessage } =
    useModelCompare(active, latestDates, tradeDate)

  // 行业暴露保留现有候选池聚合；IC、相关性与分层收益只读取后端证据。
  const factorPicks = active === 'factors' ? (modelComparePicks.length > 0 ? modelComparePicks : picks) : []
  const industryRows = useMemo(() => buildIndustryRows(factorPicks), [factorPicks])

  useEffect(() => {
    let cancelled = false

    screenerApi.getModes()
      .then(response => {
        if (cancelled) return
        const freshness = response.data?.data_freshness
        const nextLatestDates = normalizeLatestDates({
          daily_kline: response.data?.latest_trade_date || freshness?.as_of,
          ...response.data?.latest_dates,
        })
        setLatestDates(nextLatestDates)
        const syncPlan = syncPlanForMode(selectedMode)
        const today = todayDateInputValue()
        const latestTradeDate = nextLatestDates[syncPlan.tableKey] || nextLatestDates.daily_kline || ''
        if (today) {
          setTradeDate(current => current || today)
          setRunMessage(`默认使用当天交易日：${today}`)
        } else {
          setRunMessage('后端未返回最新交易日，请手动选择日期后运行')
        }
        setFreshnessSource(latestTradeDate === today ? syncPlan.tableKey : '默认当天')
      })
      .catch(() => {
        if (cancelled) return
        setRunMessage('最新交易日读取失败，请手动选择日期后运行')
        setFreshnessSource('screener/modes')
      })

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    const syncPlan = syncPlanForMode(selectedMode)
    const latestTradeDate = latestDates[syncPlan.tableKey] || latestDates.daily_kline
    if (!latestTradeDate) return
    setFreshnessSource(latestTradeDate === tradeDate ? syncPlan.tableKey : '默认当天')
  }, [latestDates, selectedMode, tradeDate])

  useEffect(() => {
    if (active !== 'factors') return

    let cancelled = false
    setFactorEvidenceLoading(true)
    setFactorEvidenceView(null)

    backtestApi.getFactorEvidence(selectedMode)
      .then(response => {
        if (!cancelled) setFactorEvidenceView(toFactorEvidenceView(response.data))
      })
      .catch(() => {
        if (!cancelled) {
          setFactorEvidenceView({ kind: 'unsupported', reasons: ['factor_evidence_request_failed'] })
        }
      })
      .finally(() => {
        if (!cancelled) setFactorEvidenceLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [active, selectedMode])

  return (
    <PrototypePage>
      <PrototypeTabs
        ariaLabel="智能选股页签"
        activeKey={active}
        onChange={(key) => {
          const tab = tabs.find(item => item.key === key)
          if (tab) navigate(tab.path)
        }}
        items={tabs.map((tab, index) => ({ ...tab, number: String(index + 1).padStart(2, '0') }))}
      />
      <PrototypePageHeader
        title={`智能选股 - ${tabs.find(tab => tab.key === active)?.label || '选股工作台'}`}
        subtitle="模型选择 · 交易日参数 · 数据同步 · 候选输出"
        dataFreshness={<DataFreshnessBar tradeDate={tradeDate} updatedAt={lastRunAt} source={freshnessSource} />}
      />
      {active === 'workbench' && (
        <WorkbenchTab
          selectedMode={selectedMode}
          onSelectMode={setSelectedMode}
          tradeDate={tradeDate}
          onTradeDateChange={setTradeDate}
          onFreshnessSourceChange={setFreshnessSource}
          lastRunAt={lastRunAt}
          onLastRunAtChange={setLastRunAt}
          latestDates={latestDates}
          resolveTradeDateForMode={resolveTradeDateForMode}
          picks={picks}
          onPicksChange={setPicks}
          runMessage={runMessage}
          onRunMessageChange={setRunMessage}
        />
      )}
      {active === 'models' && (
        <ModelsTab
          modelCompareRows={modelCompareRows}
          modelComparePicks={modelComparePicks}
          modelCompareLoading={modelCompareLoading}
          modelCompareMessage={modelCompareMessage}
          tradeDate={tradeDate}
        />
      )}
      {active === 'factors' && (
        <FactorsTab
          factorEvidenceLoading={factorEvidenceLoading}
          factorEvidenceView={factorEvidenceView}
          industryRows={industryRows}
        />
      )}
    </PrototypePage>
  )
}
