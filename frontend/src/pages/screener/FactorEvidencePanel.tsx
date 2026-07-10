import { BarChartOutlined, FundOutlined, RadarChartOutlined } from '@ant-design/icons'
import { PrototypeCard } from '../../components/prototype'
import { isReadyFactorEvidenceView, type FactorEvidenceView } from './factorEvidence'

interface FactorEvidencePanelProps {
  loading: boolean
  view: FactorEvidenceView | null
}

function formatMetric(value: number, digits = 3) {
  return Number.isFinite(value) ? value.toFixed(digits) : '—'
}

function reasonsText(reasons: unknown) {
  return Array.isArray(reasons) && reasons.every(reason => typeof reason === 'string') && reasons.length > 0
    ? reasons.join('、')
    : '后端未返回缺失条件'
}

export function FactorEvidencePanel({ loading, view }: FactorEvidencePanelProps) {
  if (loading) {
    return <div className="prototype-fallback">正在读取真实因子回测数据…</div>
  }

  if (!view || view.kind === 'unsupported') {
    return (
      <div className="prototype-fallback">
        <div>真实因子回测数据暂不可用</div>
        {view?.kind === 'unsupported' && <div className="muted">缺失：{reasonsText(view.reasons)}</div>}
      </div>
    )
  }

  if (view.kind === 'insufficient') {
    return (
      <div className="prototype-fallback">
        <div>暂无真实因子回测数据</div>
        <div className="muted">缺失：{reasonsText(view.reasons)}</div>
      </div>
    )
  }

  if (!isReadyFactorEvidenceView(view)) {
    return <div className="prototype-fallback">真实因子回测数据暂不可用</div>
  }

  return (
    <>
      <div className="row r-7-5">
        <PrototypeCard title="IC / ICIR 统计" icon={<BarChartOutlined />} meta="后端真实观测">
          {view.factors.length > 0 ? (
            <div className="tbl-scroll">
              <table className="tbl compact">
                <thead>
                  <tr>
                    <th>因子</th>
                    <th className="r">IC Mean</th>
                    <th className="r">IC Std</th>
                    <th className="r">ICIR</th>
                    <th className="r">t-stat</th>
                    <th className="r">观测数</th>
                  </tr>
                </thead>
                <tbody>
                  {view.factors.map(metric => (
                    <tr key={metric.factor}>
                      <td className="nm">{metric.label || metric.factor}</td>
                      <td className="r mono">{formatMetric(metric.ic_mean)}</td>
                      <td className="r mono">{formatMetric(metric.ic_std)}</td>
                      <td className="r mono">{formatMetric(metric.icir)}</td>
                      <td className="r mono">{formatMetric(metric.t_stat, 2)}</td>
                      <td className="r mono">{metric.observations ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="prototype-fallback">接口未返回因子指标。</div>
          )}
        </PrototypeCard>

        <PrototypeCard title="因子相关性" icon={<RadarChartOutlined />} meta="后端观测值">
          {view.correlations.length > 0 ? (
            <div className="tbl-scroll">
              <table className="tbl compact">
                <thead>
                  <tr>
                    <th>因子 A</th>
                    <th>因子 B</th>
                    <th className="r">相关性</th>
                    <th className="r">观测数</th>
                  </tr>
                </thead>
                <tbody>
                  {view.correlations.map((cell, index) => (
                    <tr key={`${cell.factor_x}-${cell.factor_y}-${index}`}>
                      <td className="nm">{cell.factor_x}</td>
                      <td className="nm">{cell.factor_y}</td>
                      <td className="r mono">{formatMetric(cell.correlation)}</td>
                      <td className="r mono">{cell.observations ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="prototype-fallback">接口未返回相关性观测。</div>
          )}
        </PrototypeCard>
      </div>

      <PrototypeCard title="因子收益率分层" icon={<FundOutlined />} meta="后端观测值">
        {view.deciles.length > 0 ? (
          <div className="tbl-scroll">
            <table className="tbl compact">
              <thead>
                <tr>
                  <th>分层</th>
                  <th>说明</th>
                  <th className="r">累计收益</th>
                  <th className="r">日均收益</th>
                  <th className="r">观测数</th>
                </tr>
              </thead>
              <tbody>
                {view.deciles.map((metric, index) => (
                  <tr key={`${metric.decile}-${index}`}>
                    <td className="nm">{metric.decile}</td>
                    <td>{metric.description || '—'}</td>
                    <td className="r mono">{formatMetric(metric.cumulative_return_pct, 2)}%</td>
                    <td className="r mono">
                      {metric.daily_return_pct === undefined ? '—' : `${formatMetric(metric.daily_return_pct, 2)}%`}
                    </td>
                    <td className="r mono">{metric.observations ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="prototype-fallback">接口未返回分层收益观测。</div>
        )}
      </PrototypeCard>
    </>
  )
}
