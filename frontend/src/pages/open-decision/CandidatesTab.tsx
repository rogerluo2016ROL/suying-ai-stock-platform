import { useState } from 'react'
import {
  DollarOutlined,
  FundOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons'
import { screenerApi } from '../../api/client'
import { message } from 'antd'
import type { RiskVerdictRecord } from '../../api/types'
import { EmptyState, PrototypeCard } from '../../components/prototype'
import { toneForRisk } from './helpers'
import type { CandidateRow } from './types'

export default function CandidatesTab({
  loading,
  error,
  candidateRows,
  verdicts,
  poolTotal,
  poolEmptyReason,
}: {
  loading: boolean
  error: string
  candidateRows: CandidateRow[]
  verdicts: RiskVerdictRecord[]
  poolTotal: number
  poolEmptyReason?: string
}) {
  const passed = candidateRows.filter(row => row.risk === '通过').length
  const planPosition = candidateRows.reduce((sum, row) => sum + Number(row.size.replace('%', '')), 0)
  const empty = candidateRows.length === 0
  const [watchingCode, setWatchingCode] = useState('')
  // DEF-1: 加入自选——调 watchlistApi.addWatchlist({code,name})，成功/失败(fallback_reason) toast + listWatchlist 刷新
  const handleWatch = async (code: string, name?: string) => {
    if (watchingCode) return
    setWatchingCode(code)
    try {
      const response = await screenerApi.addWatchlist({ code, name })
      const fallback = response.data?.fallback_reason
      if (response.data?.record) {
        message.success(`已加入自选：${code} ${name || ''}`.trim())
      } else if (fallback) {
        message.error(fallback)
      } else {
        message.success(`已加入自选：${code}`)
      }
      screenerApi.listWatchlist().catch(() => message.error('刷新自选列表失败，请手动刷新'))
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      message.error(detail || '加入自选失败，请稍后重试')
    } finally {
      setWatchingCode('')
    }
  }
  return (
    <>
      <section className="workflow-nav">
        <div className="workflow-track" aria-label="P0 主链路">
          <span className="workflow-step active"><span className="workflow-index">01</span><span className="workflow-copy"><span className="workflow-label">P0 主链路</span><span className="workflow-desc">候选池</span></span></span>
          <span className="workflow-arrow">-&gt;</span>
          <span className="workflow-step"><span className="workflow-index">02</span><span className="workflow-copy"><span className="workflow-label">方案管理</span><span className="workflow-desc">生成方案</span></span></span>
          <span className="workflow-arrow">-&gt;</span>
          <span className="workflow-step"><span className="workflow-index">03</span><span className="workflow-copy"><span className="workflow-label">风控闸门</span><span className="workflow-desc">RiskVerdict</span></span></span>
        </div>
      </section>

      <div className="row r-6-4">
        <PrototypeCard
          title="多源候选池"
          icon={<FundOutlined />}
          meta={poolTotal > 0 ? `Candidate 对象预览 · 候选池 ${poolTotal} 条已持久化` : 'Candidate 对象预览 · chain + screener 多源融合去重'}
        >
          {empty ? (
            <EmptyState
              title={loading ? '候选池加载中' : '候选池暂无数据'}
              detail={loading
                ? '正在拉取 chain/candidates 与 screener/candidate-pool。'
                : error || poolEmptyReason || 'fallback_reason：chain 与 screener 候选池均无数据，等待选股 / 竞价 / 信号写入候选池后展示。'}
            />
          ) : (
            <table className="tbl">
              <thead><tr><th>#</th><th>代码</th><th>名称</th><th>来源</th><th className="r">综合评分</th><th>风控</th><th className="r">建议仓位</th><th>操作</th></tr></thead>
              <tbody>
                {candidateRows.map((row, index) => (
                <tr key={row.code}>
                  <td>{index + 1}</td>
                  <td className="code">{row.code}</td>
                  <td className="nm">{row.name}</td>
                  <td>{row.source}</td>
                  <td className="r up">{row.score}</td>
                  <td><span className={`tag ${toneForRisk(row.risk)}`}>{row.risk}</span></td>
                  <td className="r mono">{row.size}</td>
                  <td className="r"><button type="button" className="btn sm ghost" onClick={() => handleWatch(row.code, row.name)} disabled={watchingCode === row.code} title="加入自选">{watchingCode === row.code ? '加入中…' : '加入自选'}</button></td>
                </tr>
              ))}
              </tbody>
            </table>
          )}
        </PrototypeCard>

        <div className="grid">
          <PrototypeCard title="风控排查" icon={<SafetyCertificateOutlined />} meta="RiskVerdict">
            {(verdicts.length ? verdicts.slice(0, 4).map(item => `${item.symbol || item.candidate_id || item.scope}: ${item.result}`) : ['暂无风控判定']).map((item, index) => (
              <div className="li-row" key={item}>
                <span className="li-badge down">{index + 1}</span>
                <div className="li-main"><div className="n">{item}</div><div className="s">已写入候选对象风险字段</div></div>
              </div>
            ))}
          </PrototypeCard>

          <PrototypeCard title="交易方案预览" icon={<DollarOutlined />} meta="Plan 草稿">
            <div className="risk-banner safe">
              <strong>风控预检: {candidateRows.length ? `${passed}/${candidateRows.length} 通过` : '等待候选'}</strong>
              <span>{candidateRows.length}只候选 · 计划仓位 {planPosition}% · 最大单票 30% · 禁止追高价差 &gt; 2%</span>
            </div>
            <div className="od-actions mt14">
              <button type="button" className="btn primary">生成方案</button>
              <button type="button" className="btn ghost">保存为手动方案</button>
            </div>
          </PrototypeCard>
        </div>
      </div>
    </>
  )
}
