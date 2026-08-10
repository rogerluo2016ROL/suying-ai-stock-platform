import { useEffect, useMemo, useState } from 'react'
import { screenerApi } from '../../api/client'
import type { ScreenerPick } from '../../api/types'
import {
  averageScore,
  createTradeDateResolver,
  modelCompareModes,
  modelNameById,
  syncPlanForMode,
} from './helpers'
import type { ModelCompareRow, ModelCompareRunRow } from './types'

// models 与 factors tab 都需要模型对比 picks（factors 仅用于现有行业暴露），
// 故在两个 tab 都触发；workbench 不触发（工作台有自己的 runScreener 路径）。
export function useModelCompare(active: string, latestDates: Record<string, string>, tradeDate: string) {
  const [modelCompareRows, setModelCompareRows] = useState<ModelCompareRow[]>([])
  const [modelComparePicks, setModelComparePicks] = useState<ScreenerPick[]>([])
  const [modelCompareLoading, setModelCompareLoading] = useState(false)
  const [modelCompareMessage, setModelCompareMessage] = useState('等待模型对比运行')

  const resolveTradeDateForMode = useMemo(
    () => createTradeDateResolver(latestDates, tradeDate),
    [latestDates, tradeDate],
  )

  useEffect(() => {
    if (active !== 'models' && active !== 'factors') return
    if (Object.keys(latestDates).length === 0) return
    let cancelled = false
    setModelCompareLoading(true)
    setModelCompareMessage('正在按最新可用数据运行模型对比')

    Promise.allSettled(
      modelCompareModes.map(async (modeId): Promise<ModelCompareRunRow> => {
        const runDate = resolveTradeDateForMode(modeId)
        const response = await screenerApi.run(modeId, 10, runDate)
        const nextPicks = response.data?.picks || []
        const row: ModelCompareRunRow = {
          modeId,
          name: modelNameById(modeId),
          tradeDate: String(response.data?.trade_date || response.data?.data_freshness?.as_of || runDate || '').slice(0, 10),
          source: response.data?.data_freshness?.source || syncPlanForMode(modeId).tableKey,
          count: nextPicks.length,
          avgScore: averageScore(nextPicks),
          picks: nextPicks.map(pick => ({
            ...pick,
            entry_reason: `${modelNameById(modeId)}；${pick.entry_reason || ''}`,
          })),
        }
        if (nextPicks[0]) row.topPick = nextPicks[0]
        return row
      }),
    ).then(results => {
      if (cancelled) return
      const rows = results
        .filter((result): result is PromiseFulfilledResult<ModelCompareRunRow> => result.status === 'fulfilled')
        .map(result => result.value)
      setModelCompareRows(rows)
      setModelComparePicks(rows.flatMap(row => row.picks).slice(0, 30))
      setModelCompareMessage(rows.length > 0 ? '模型对比完成' : '模型对比未返回可用结果')
    }).catch(error => {
      if (cancelled) return
      setModelCompareRows([])
      setModelComparePicks([])
      setModelCompareMessage(error instanceof Error ? error.message : '模型对比运行失败')
    }).finally(() => {
      if (!cancelled) setModelCompareLoading(false)
    })

    return () => {
      cancelled = true
    }
  }, [active, latestDates, tradeDate, resolveTradeDateForMode])

  return { modelCompareRows, modelComparePicks, modelCompareLoading, modelCompareMessage }
}
