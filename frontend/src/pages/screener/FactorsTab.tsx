import { RadarChartOutlined } from '@ant-design/icons'
import { PrototypeCard } from '../../components/prototype'
import { FactorEvidencePanel } from './FactorEvidencePanel'
import type { FactorEvidenceView } from './factorEvidence'
import type { IndustryRow } from './types'

type FactorsTabProps = {
  factorEvidenceLoading: boolean
  factorEvidenceView: FactorEvidenceView | null
  industryRows: IndustryRow[]
}

export function FactorsTab({ factorEvidenceLoading, factorEvidenceView, industryRows }: FactorsTabProps) {
  return (
    <>
      <div className="guide-bar">
        <span className="guide-lead neu">证据原则:</span>
        <span>仅展示回测服务返回的真实观测</span>
        <span className="arrow muted">·</span>
        <span>观测不足或接口不支持时不生成指标</span>
      </div>

      <FactorEvidencePanel loading={factorEvidenceLoading} view={factorEvidenceView} />

      {/* Row 3: 行业因子暴露 */}
      <PrototypeCard title="行业因子暴露" icon={<RadarChartOutlined />} meta="按行业聚合">
        {industryRows.length > 0 ? (
          <div className="tbl-scroll">
            <table className="tbl">
              <thead>
                <tr>
                  <th>行业板块</th>
                  <th className="r">偏离度</th>
                  <th className="c">暴露程度</th>
                  <th className="r">股票数</th>
                </tr>
              </thead>
              <tbody>
                {industryRows.map(row => (
                  <tr key={row.industry}>
                    <td className="nm">{row.industry}</td>
                    <td className={`r mono ${row.avg >= 0 ? 'up' : 'down'}`}>{row.avg >= 0 ? '+' : ''}{row.avg.toFixed(2)}</td>
                    <td className="c"><span className={`exp-tag ${row.level}`}>{row.level === 'high' ? '偏高' : row.level === 'low' ? '偏低' : '中性'}</span></td>
                    <td className="r mono">{row.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="prototype-fallback">候选股缺少行业字段，无法计算行业因子暴露。</div>
        )}
      </PrototypeCard>

      <div className="footer-bar">
        <span>智能选股 · 因子分析 | 盘后 15:42</span>
        <span className="sep" />
        <span>回测证据: backtest-service /backtest/factor-evidence</span>
        <span className="sep" />
        <span>候选分数不参与 IC、相关性或分层收益计算</span>
      </div>
    </>
  )
}
