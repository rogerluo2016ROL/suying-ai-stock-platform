import {
  BarChartOutlined,
  CheckCircleOutlined,
  FundOutlined,
  LineChartOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { PrototypeCard } from '../../components/prototype'
import { toneForRisk } from './helpers'
import type { SignalRow } from './types'

export default function SignalsTab({
  loading,
  error,
  signalRows,
}: {
  loading: boolean
  error: string
  signalRows: SignalRow[]
}) {
  const selected = signalRows[0]
  const dimensions = selected?.dimensions || [
    { label: '技术面', value: 0 },
    { label: '资金面', value: 0 },
    { label: '基本面', value: 0 },
    { label: '情绪', value: 0 },
    { label: '置信度', value: 0 },
    { label: '风控', value: 0 },
  ]
  const buyCount = signalRows.filter(row => row.signal.includes('买')).length
  const watchCount = signalRows.filter(row => row.watchlist).length

  return (
    <>
      <section className="od-locked-banner">
        <strong>锁定板块:</strong>
        <span className="chip active">实时信号 <b>{signalRows.length}</b></span>
        <span className="chip active">买入候选 <b>{buyCount}</b></span>
        <button type="button" className="btn sm ghost">清除锁定</button>
      </section>

      <section className="od-signal-filter-row">
        <div className="signal-filter-bar">
          <button type="button" className="filter-btn active">全部 <span className="mono">{signalRows.length}</span></button>
          <button type="button" className="filter-btn">仅买入 <span className="mono">{buyCount}</span></button>
          <button type="button" className="filter-btn">仅自选 <span className="mono">{watchCount}</span></button>
        </div>
        <div className="signal-filter-bar">
          <span className="sort-label">排序:</span>
          <button type="button" className="filter-btn active">信号评分 ▼</button>
          <button type="button" className="filter-btn">一致性</button>
          <button type="button" className="filter-btn">风险</button>
        </div>
      </section>

      <div className="od-signal-layout">
        <div className="od-signal-left">
        <PrototypeCard title="信号扫描" icon={<ThunderboltOutlined />} meta="验证工作台 · 逐条确认信号 · Kronos 交叉验证 · 一键推送候选池">
          <table className="tbl od-verify-table">
            <thead><tr><th>代码</th><th>名称</th><th>信号</th><th className="r">评分</th><th>Kronos预测</th><th>一致性</th><th>风险</th><th className="r">操作</th></tr></thead>
            <tbody>
              {signalRows.map(row => (
                <tr className={row.code === selected?.code ? 'picked' : ''} key={row.code}>
                  <td className="code">{row.code}</td>
                  <td className="nm">{row.name}{row.watchlist && <span className="in-pool-tag">自选</span>}</td>
                  <td><span className={row.score >= 70 ? 'tag t-up' : row.score >= 60 ? 'tag t-warn' : 'tag t-mute'}>{row.signal}</span></td>
                  <td className="r mono">{row.score}</td>
                  <td className={row.kronos.startsWith('+') ? 'up' : 'down'}>{row.kronos} -&gt; {row.target}</td>
                  <td><span className={row.consistency === '双确认' ? 'tag t-down' : row.consistency === '相悖' ? 'tag t-warn' : 'tag t-mute'}>{row.consistency}</span></td>
                  <td><span className={`tag ${toneForRisk(row.risk)}`}>{row.risk}</span></td>
                  <td className="r"><button type="button" className="btn sm ghost">{row.action}</button></td>
                </tr>
              ))}
              {signalRows.length === 0 && <tr><td colSpan={8} className="prototype-panel-note">{loading ? '实时信号加载中。' : error || '暂无实时信号。'}</td></tr>}
            </tbody>
          </table>
          <div className="od-batch-bar">
            <button type="button" className="btn sm primary">批量确认买入信号</button>
            <button type="button" className="btn sm ghost">一键排除风险标的</button>
            <span>点击行查看详情</span>
            <b>逐条确认决策</b>
          </div>
          <div className="od-summary-bar">
            已处理 <b>0</b>/<span>{signalRows.length}</span> · 已确认 <b className="down">0</b> · 已降级 <b className="warn">0</b> · 已排除 <b className="up">0</b>
          </div>
        </PrototypeCard>

        <PrototypeCard title="信号拆解" icon={<BarChartOutlined />} meta="信号 + 预测 + 风控">
          <div className="od-signal-stack">
            {dimensions.map(item => (
              <div className="watch-sector-bar" key={item.label}>
                <span>{item.label}</span>
                <div><i style={{ width: `${item.value}%` }} /></div>
                <b>{item.value}</b>
              </div>
            ))}
          </div>
        </PrototypeCard>
      </div>

      <aside className="od-signal-rail">
        <PrototypeCard title="选中股票" icon={<FundOutlined />} meta={selected?.code || '-'}>
          <div className="od-selected-stock">
            <span className="code">{selected?.code || '-'}</span>
            <b>{selected?.name || '暂无信号'}</b>
            <span className="mono">¥{selected?.price || '-'}</span>
          </div>
          <div className="od-signal-big-tag">{selected?.signal || '等待'} <span>{selected?.score || 0}分</span></div>
          <div className="od-detail-title">六维评分</div>
          {dimensions.map(item => (
            <div className="watch-sector-bar" key={item.label}>
              <span>{item.label}</span>
              <div><i style={{ width: `${item.value}%` }} /></div>
              <b>{item.value}</b>
            </div>
          ))}
        </PrototypeCard>

        <PrototypeCard title="Kronos 30日预测" icon={<LineChartOutlined />} meta={selected ? `${selected.code} ${selected.name}` : '暂无信号'}>
          <div className="od-kronos-dir">
            <span>↗</span>
            <div>
              <b className="mono">{selected?.price || '-'} -&gt; <span className="up">{selected?.target || '-'}</span></b>
              <strong>{selected?.kronos || '模型预测需等待 prediction 服务返回'}</strong>
            </div>
          </div>
          <div className="bar mt14"><i style={{ width: `${selected?.confidence || 0}%` }} /></div>
          <div className="prototype-panel-note mt14">置信度 {selected?.confidence || 0}% · {selected?.consistency || '等待信号'}</div>
        </PrototypeCard>

        <PrototypeCard title="信号+预测 方向一致" icon={<CheckCircleOutlined />}>
          <div className="od-verdict">
            <span>✓</span>
            <div>
              <strong>方向一致</strong>
              <p>信号强度: {selected?.signal || '-'} {selected?.score || 0}分 · 多因子共振 · {selected?.risk || '待风控'}</p>
            </div>
          </div>
        </PrototypeCard>

        <PrototypeCard title="风险检查" icon={<SafetyCertificateOutlined />} meta="RiskVerdict">
          {[
            `信号风险: ${selected?.risk || '待风控'}`,
            `置信度: ${selected?.confidence || 0}%`,
            `操作建议: ${selected?.action || '-'}`,
            `一致性: ${selected?.consistency || '-'}`,
          ].map((item, index) => (
            <div className="od-risk-row" key={item}>
              <span>{index + 1}. {item}</span>
              <b>{selected?.risk === '通过' && index === 0 ? '自动通过' : '执行前复核'}</b>
            </div>
          ))}
        </PrototypeCard>

        <PrototypeCard title="决策分类" icon={<FundOutlined />} meta="候选池推送">
          <div className="od-decision-group"><strong>已确认</strong><span>强买 + 预测一致 + 风控通过</span></div>
          <div className="od-decision-group"><strong>降级</strong><span>Kronos 相悖或置信度不足</span></div>
          <div className="od-decision-group"><strong>排除</strong><span>风险不通过或高价股限制</span></div>
          <button type="button" className="btn primary od-push-btn mt14">一键推送已确认 -&gt; 候选池</button>
          <button type="button" className="btn ghost od-push-btn mt14">查看候选池 -&gt;</button>
        </PrototypeCard>
      </aside>
    </div>
    </>
  )
}
