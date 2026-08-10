import {
  CheckCircleOutlined,
  DollarOutlined,
  FundOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import type { DecisionContextRecord, TradeAccount } from '../../api/types'
import { PrototypeCard } from '../../components/prototype'
import { formatMoney } from './helpers'
import type { OrderRow, PositionRow } from './types'

export default function ExecutionTab({
  loading,
  error,
  account,
  orderRows,
  positionRows,
  contexts,
}: {
  loading: boolean
  error: string
  account?: TradeAccount
  orderRows: OrderRow[]
  positionRows: PositionRow[]
  contexts: DecisionContextRecord[]
}) {
  const filledOrders = orderRows.filter(row => row.status === '已成交').length
  const pendingOrders = orderRows.length - filledOrders
  return (
    <>
      <section className="od-account-bar card">
        {[
          ['总资产', formatMoney(account?.total_assets), '账户 account.paper'],
          ['可用', formatMoney(account?.available), '可下单资金'],
          ['今日盈亏', formatMoney(account?.total_pnl), 'trade/account'],
          ['总仓位', account?.market_value && account?.total_assets ? `${Math.round((account.market_value / account.total_assets) * 100)}%` : '-', '阈值以后端风控返回为准'],
        ].map(([label, value, sub]) => (
          <div key={label}>
            <span>{label}</span>
            <b className={`mono ${label === '今日盈亏' ? 'up' : ''}`}>{value}</b>
            <small>{sub}</small>
          </div>
        ))}
      </section>

      <div className="row r-6-4">
        <div className="grid">
          <PrototypeCard title="今日订单" icon={<DollarOutlined />} meta={`${orderRows.length}单 · 成交${filledOrders} · 待成交${pendingOrders}`}>
            <table className="tbl">
              <thead><tr><th>时间</th><th>代码</th><th>名称</th><th>方向</th><th className="r">价格</th><th className="r">数量</th><th>状态</th></tr></thead>
              <tbody>
                {orderRows.map(row => (
                  <tr key={`${row.time}-${row.code}`}>
                    <td className="mono">{row.time}</td>
                    <td className="code">{row.code}</td>
                    <td className="nm">{row.name}</td>
                    <td><span className="tag t-up">{row.dir}</span></td>
                    <td className="r mono">{row.price}</td>
                    <td className="r mono">{row.qty}</td>
                    <td><span className={`tag ${row.status === '已成交' ? 't-down' : row.status === '待成交' ? 't-warn' : 't-neu'}`}>{row.status}</span></td>
                  </tr>
                ))}
                {orderRows.length === 0 && <tr><td colSpan={7} className="prototype-panel-note">{loading ? '订单加载中。' : error || '暂无订单。'}</td></tr>}
              </tbody>
            </table>
          </PrototypeCard>

          <PrototypeCard title="持仓" icon={<FundOutlined />} meta="实时同步 trade-service">
            <table className="tbl">
              <thead><tr><th>代码</th><th>名称</th><th className="r">市值</th><th className="r">盈亏</th><th className="r">权重</th></tr></thead>
              <tbody>
                {positionRows.map(row => (
                  <tr key={row.code}>
                    <td className="code">{row.code}</td>
                    <td className="nm">{row.name}</td>
                    <td className="r mono">{row.value}</td>
                    <td className="r up">{row.pnl}</td>
                    <td className="r mono">{row.weight}</td>
                  </tr>
                ))}
                {positionRows.length === 0 && <tr><td colSpan={5} className="prototype-panel-note">{loading ? '持仓加载中。' : '暂无持仓。'}</td></tr>}
              </tbody>
            </table>
          </PrototypeCard>
        </div>

        <div className="grid">
          <PrototypeCard title="自动交易策略" icon={<ThunderboltOutlined />} meta="paper">
            {(contexts.length ? contexts.slice(0, 4).map(item => `${item.source_type}: ${item.intent}`) : ['暂无执行上下文']).map((item, index) => (
              <div className="li-row" key={item}>
                <span className={`li-badge ${index === 0 ? 'down' : 'neu'}`}>{index + 1}</span>
                <div className="li-main"><div className="n">{item}</div><div className="s">StrategyExecutionContext 已记录</div></div>
              </div>
            ))}
          </PrototypeCard>

          <PrototypeCard title="今日方案" icon={<CheckCircleOutlined />} meta={contexts[0]?.plan_id || '暂无方案'}>
            <div className="risk-banner accent">
              <strong>{contexts.length ? '开盘决策上下文已记录' : '等待方案生成'}</strong>
              <span>上下文 {contexts.length} 条 · 已下单 {orderRows.length} 只 · 待确认 {pendingOrders} 只</span>
            </div>
            <div className="od-actions mt14">
              <button type="button" className="btn primary">一键启动自动交易</button>
              <button type="button" className="btn ghost">去交易中心手动下单</button>
              <button type="button" className="btn ghost">删除</button>
            </div>
          </PrototypeCard>

          <PrototypeCard title="需关注" icon={<SafetyCertificateOutlined />}>
            {orderRows.filter(row => row.status !== '已成交').map((row, index) => (
              <div className="li-row" key={row.code}>
                <span className="li-badge warn">{index + 1}</span>
                <div className="li-main"><div className="n">{row.name} {row.status}</div><div className="s">来自订单接口</div></div>
              </div>
            ))}
            {orderRows.filter(row => row.status !== '已成交').length === 0 && <div className="prototype-panel-note">暂无执行提醒。</div>}
          </PrototypeCard>
        </div>
      </div>
    </>
  )
}
