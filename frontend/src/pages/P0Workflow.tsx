import { CheckCircleOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { P0WorkflowNav } from '../components/layout'
import {
  DataDomainBadge,
  LineageChips,
  MetricCard,
  PrototypeCard,
  PrototypePage,
  PrototypePageHeader,
  RiskBanner,
  SideRail,
} from '../components/prototype'

const objects = [
  { name: 'Candidate', cn: '候选池', owner: 'screener/open-decision', status: '已生成', detail: '股票、来源模式、评分、证据、账户作用域' },
  { name: 'Plan', cn: '方案管理', owner: 'strategy-service', status: '待风控', detail: '候选快照、资金、仓位、执行约束' },
  { name: 'Order', cn: '下单面板', owner: 'trade-service', status: '草稿', detail: '方向、价格、数量、账户、交易模式' },
  { name: 'RiskVerdict', cn: '风控闸门', owner: 'trade-service', status: '强制', detail: '通过、警告、拒绝、人工复核与规则明细' },
  { name: 'BacktestReview', cn: '回测复盘', owner: 'backtest-service', status: '回填', detail: '订单、风控和决策上下文聚合归因' },
]

export default function P0Workflow() {
  return (
    <PrototypePage>
      <PrototypePageHeader
        title="P0 主链路"
        subtitle="候选池 -> 方案管理 -> 下单面板 -> 风控闸门 -> 回测复盘"
        actions={[
          { key: 'paper', label: '模拟盘优先', active: true },
          { key: 'live', label: '实盘锁定', tone: 'warn' },
        ]}
      />
      <P0WorkflowNav currentStep="candidate" />

      <div className="kpis">
        <MetricCard label="链路对象" value="5" sub="公共契约" tone="accent" />
        <MetricCard label="账户域" value="tenant/user/account" sub="私有数据隔离" tone="muted" />
        <MetricCard label="风控闸门" value="必过" sub="Order 前置" tone="warn" />
        <MetricCard label="实盘路径" value="Gate" sub="人工放行" tone="down" />
      </div>

      <div className="row r-6-4">
        <PrototypeCard title="主链路对象" icon={<CheckCircleOutlined />} meta="P0 contract">
          <table className="tbl">
            <thead><tr><th>对象</th><th>业务节点</th><th>Owner</th><th>状态</th><th>字段重点</th></tr></thead>
            <tbody>
              {objects.map(item => (
                <tr key={item.name}>
                  <td className="nm">{item.name}</td>
                  <td>{item.cn}</td>
                  <td className="code">{item.owner}</td>
                  <td><span className="tag t-neu">{item.status}</span></td>
                  <td>{item.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </PrototypeCard>
        <SideRail title="执行闸门" meta="paper/live">
          <DataDomainBadge domain="account" label="账户私有链路" />
          <RiskBanner status="warn" title="实盘默认关闭" detail="模拟盘链路跑通后，QMT/券商实盘仍必须经过券商配置、风控判定和审计留痕。" />
          <LineageChips
            items={[
              { label: '候选', value: 'CAND-*' },
              { label: 'Risk', value: '强制预检', tone: 'warn' },
              { label: 'Audit', value: '全量留痕', tone: 'accent' },
            ]}
          />
        </SideRail>
      </div>

      <div className="row r-3">
        {['候选进入方案', '方案生成订单', '订单触发风控'].map((item, index) => (
          <PrototypeCard key={item} title={item} icon={<SafetyCertificateOutlined />} meta={`Step ${index + 1}`}>
            <div className="prototype-panel-note">
              {index === 0 && '候选保留来源模式、评分、证据和账户归属，避免公共数据与私有方案混写。'}
              {index === 1 && '订单草稿必须带 plan_id、candidate_id、decision_context_id。'}
              {index === 2 && 'RiskVerdict 未通过时只能保存草稿，不能进入实盘提交。'}
            </div>
          </PrototypeCard>
        ))}
      </div>
    </PrototypePage>
  )
}
