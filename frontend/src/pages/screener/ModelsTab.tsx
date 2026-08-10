import { useMemo, useState } from 'react'
import { BarChartOutlined, FundOutlined } from '@ant-design/icons'
import { message } from 'antd'
import { PrototypeCard } from '../../components/prototype'
import { screenerApi } from '../../api/client'
import type { ScreenerPick } from '../../api/types'
import { lightTokens } from '../../styles/tokens'
import {
  buildConsensusRows,
  buildCrossModelScores,
  consensusByCumulative,
  formatScore,
  indicatorToneColor,
  modelCompareModes,
  modelNameById,
  MODEL_TAG_TONE,
  shortNameForModel,
  STAR_TIERS,
} from './helpers'
import type { ConsensusRow, ModelCompareRow } from './types'

type ModelsTabProps = {
  modelCompareRows: ModelCompareRow[]
  modelComparePicks: ScreenerPick[]
  modelCompareLoading: boolean
  modelCompareMessage: string
  tradeDate: string
}

export function ModelsTab({
  modelCompareRows,
  modelComparePicks,
  modelCompareLoading,
  modelCompareMessage,
  tradeDate,
}: ModelsTabProps) {
  const [selectedConsensusCode, setSelectedConsensusCode] = useState('')
  const [recordingPool, setRecordingPool] = useState(false)

  // ===== 3.2 model-compare 派生：共识矩阵 + 跨模型评分 =====
  const consensusRows = useMemo(() => buildConsensusRows(modelComparePicks), [modelComparePicks])
  const maxStar = useMemo(() => consensusRows.reduce((m, r) => Math.max(m, r.stars), 0), [consensusRows])
  const selectedConsensus = useMemo(
    () => consensusRows.find(r => r.code === selectedConsensusCode) || consensusRows[0],
    [consensusRows, selectedConsensusCode],
  )
  const crossModelScores = useMemo(
    () => buildCrossModelScores(selectedConsensus, modelComparePicks),
    [selectedConsensus, modelComparePicks],
  )

  const addConsensusToPool = (row: ConsensusRow) => {
    // 把选中星级最高的标的加入候选池（复用既有 recordCandidatePool 路径）
    const candidates = consensusRows
      .filter(r => r.stars >= maxStar)
      .map((p, idx) => ({
        code: p.code,
        name: p.name || '',
        score: Number(p.bestScore ?? 0),
        grade: 'A' as const,
        rank: idx + 1,
      }))
    if (candidates.length === 0) return
    setRecordingPool(true)
    screenerApi.recordCandidatePool({
      source_module: 'screener',
      source_mode: 'model_compare',
      trade_date: tradeDate,
      name: `model_compare-${tradeDate}`,
      candidates,
    }).then(response => {
      const poolId = response.data?.pool_id || response.data?.id?.toString() || ''
      message.success(`已加入候选池 ${poolId}（${candidates.length} 只 ★${'★'.repeat(Math.max(1, maxStar - 1))}）`)
    }).catch(error => {
      message.error(error instanceof Error ? error.message : '加入候选池失败')
    }).finally(() => setRecordingPool(false))
    void row
  }

  return (
    <>
      {/* 模型选择器（4 模型默认全选，token 化色） */}
      <div className="model-selector">
        {modelCompareModes.map(modeId => {
          const name = modelNameById(modeId)
          const short = shortNameForModel(name)
          return (
            <label className="check checked" key={modeId}>
              <input type="checkbox" checked readOnly />
              <span className={`model-chip ${MODEL_TAG_TONE[short] || 'bi'}`}>{short}</span>
              {name}
            </label>
          )
        })}
        <span
          className="run-state"
          style={{ background: lightTokens.down, color: lightTokens.surface }}
        >
          {modelCompareLoading ? '运行中…' : modelCompareRows.length > 0 ? '✓ 已完成' : '等待数据'}
        </span>
      </div>

      {/* 共识统计条：每个模型 N 只 ∩ ... = 共识只数 */}
      {modelCompareRows.length > 0 ? (
        <div className="stats-bar">
          {modelCompareRows.map((row, idx) => (
            <span className="stats-group" key={row.modeId}>
              {idx > 0 && <span className="sep-icon">∩</span>}
              <span className="step">
                <span className={`model-chip sm ${MODEL_TAG_TONE[shortNameForModel(row.name)] || 'bi'}`}>
                  {shortNameForModel(row.name)}
                </span>
                <span className="count">{row.count}只</span>
              </span>
              {idx > 0 && (
                <span className={`step hl ${idx === modelCompareRows.length - 1 ? 'final' : ''}`}>
                  <span className="count">{consensusByCumulative(modelCompareRows, idx)}只</span>
                </span>
              )}
            </span>
          ))}
          <span className="rate">
            最终共识率{' '}
            <span className="val warn">{modelComparePicks.length}/{modelCompareRows.reduce((s, r) => s + r.count, 0) || 0} 只</span>
          </span>
        </div>
      ) : (
        <div className="prototype-fallback">{modelCompareLoading ? '正在运行模型对比...' : modelCompareMessage}</div>
      )}

      {/* 主区：左共识矩阵 + 右跨模型评分对比 */}
      <div className="row r-7-5">
        <PrototypeCard title="共识矩阵" icon={<BarChartOutlined />} meta={`共 ${consensusRows.length} 只标的`}>
          {/* 星级筛选 tab（仅展示，按 stars 分桶） */}
          <div className="filter-tabs">
            <span
              className="filter-tab active"
              role="tab"
              aria-selected="true"
            >
              全部 {consensusRows.length}
            </span>
            {STAR_TIERS.map(tier => {
              const n = consensusRows.filter(r => r.stars === tier.value).length
              if (n === 0) return null
              return (
                <span className="filter-tab" role="tab" key={tier.value} aria-selected="false">
                  {tier.label} {n}
                </span>
              )
            })}
          </div>
          {consensusRows.length > 0 ? (
            <div className="tbl-scroll">
              <table className="tbl">
                <thead>
                  <tr>
                    <th>代码</th>
                    <th>名称</th>
                    <th className="r">最新价</th>
                    <th className="r">涨跌幅</th>
                    <th className="c">共识度</th>
                    <th>选中模型</th>
                  </tr>
                </thead>
                <tbody>
                  {consensusRows.map(row => (
                    <tr
                      key={row.code}
                      className={selectedConsensusCode === row.code ? 'picked' : undefined}
                      onClick={() => setSelectedConsensusCode(row.code)}
                    >
                      <td className="code neu">{row.code}</td>
                      <td className="nm">{row.name}</td>
                      <td className={`r mono ${row.changePct === undefined ? '' : row.changePct >= 0 ? 'up' : 'down'}`}>
                        {row.price !== undefined ? row.price.toFixed(2) : '--'}
                      </td>
                      <td className={`r mono ${row.changePct === undefined ? '' : row.changePct >= 0 ? 'up' : 'down'}`}>
                        {row.changePct === undefined ? '--' : `${row.changePct >= 0 ? '+' : ''}${row.changePct.toFixed(1)}%`}
                      </td>
                      <td className="c stars warn">{'★'.repeat(row.stars)}</td>
                      <td>
                        {row.models.map((m, i) => (
                          <span className={`model-chip ${m.tone}`} key={i}>{m.short}</span>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="prototype-fallback">模型已运行，但当前没有候选股票。</div>
          )}
        </PrototypeCard>

        {/* 右：跨模型评分对比（选中股的多模型评分卡 + 指标条） */}
        <PrototypeCard title="跨模型评分对比" icon={<FundOutlined />}>
          {selectedConsensus ? (
            <div className="score-panel">
              <div className="stock-header">
                <span className="stk-code mono">{selectedConsensus.code}</span>
                <span className="stk-name">{selectedConsensus.name}</span>
                <span className={`stk-price mono ${selectedConsensus.changePct === undefined ? '' : selectedConsensus.changePct >= 0 ? 'up' : 'down'}`}>
                  {selectedConsensus.price !== undefined ? `¥${selectedConsensus.price.toFixed(2)}` : '--'}
                </span>
              </div>
              {crossModelScores.map((entry, idx) => (
                <div className="score-card" key={idx}>
                  <div className="sc-header">
                    <span className="sc-model">
                      <span className={`model-chip ${MODEL_TAG_TONE[entry.short] || 'bi'}`}>{entry.short}</span>
                      {entry.modelName}
                    </span>
                    <div>
                      <span className="sc-score neu">{entry.score !== undefined ? formatScore(entry.score) : '--'}</span>
                    </div>
                  </div>
                  {entry.indicators.map(ind => (
                    <div className="indicator-row" key={ind.label}>
                      <span className="sc-lbl">{ind.label}</span>
                      <span className="sc-bar">
                        <span
                          className="sc-bar-fill"
                          style={{ width: `${ind.width}%`, background: indicatorToneColor(ind.tone) }}
                        />
                      </span>
                      <span className="sc-val mono">{ind.value === null ? '--' : formatScore(ind.value)}</span>
                    </div>
                  ))}
                </div>
              ))}
              <button
                type="button"
                className="btn-accent btn-block"
                onClick={() => addConsensusToPool(selectedConsensus)}
              >
                + 加入候选池（{consensusRows.filter(r => r.stars >= maxStar).length}只 {STAR_TIERS[0]?.label}）
              </button>
            </div>
          ) : (
            <div className="prototype-fallback">点击左侧矩阵中的标的，查看跨模型评分差异。</div>
          )}
        </PrototypeCard>
      </div>

      <div className="footer-bar">
        <span>智能选股 · 模型对比 | 盘后运行</span>
        <span className="sep" />
        <span>毕=毕师傅 匪=匪爷 秋=秋神 长=长线</span>
        <span className="sep" />
        <span>数据来源: screener-service POST /screener/run</span>
      </div>
    </>
  )
}
