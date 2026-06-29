import { useMemo } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { AlertOutlined, AuditOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { P0WorkflowNav } from '../components/layout'
import {
  DataDomainBadge,
  LineageChips,
  MetricCard,
  PrototypeCard,
  PrototypePage,
  PrototypePageHeader,
  PrototypeTabs,
  RiskBanner,
  SideRail,
} from '../components/prototype'

const tabs = [
  { key: 'dashboard', path: '/risk', label: '风控总览', subLabel: '风险闸门' },
  { key: 'overview', path: '/risk/overview', label: '风险总览', subLabel: '组合暴露' },
  { key: 'positions', path: '/risk/positions', label: '持仓风险', subLabel: '集中度' },
  { key: 'strategies', path: '/risk/strategies', label: '策略风险', subLabel: '回撤' },
  { key: 'market', path: '/risk/market', label: '市场风险', subLabel: '事件/波动' },
  { key: 'audit', path: '/risk/audit', label: '事件审计', subLabel: '留痕' },
]

const auditRows = [
  { verdict: 'RV-B3', order: 'ORD-B3', context: 'CTX-B3-3', result: 'pass', scope: 'order', rule: '资金充足 / 仓位上限' },
  { verdict: 'RV-W1', order: 'ORD-W1', context: 'CTX-W1', result: 'warn', scope: 'order', rule: '单票集中度接近阈值' },
  { verdict: 'RV-R1', order: '草稿', context: 'CTX-R1', result: 'reject', scope: 'plan', rule: '黑名单 / 流动性不足' },
]

function activeKey(pathname: string) {
  const last = pathname.split('/').filter(Boolean).pop()
  if (last && tabs.some(tab => tab.key === last)) return last
  return 'dashboard'
}

export default function RiskControl() {
  const location = useLocation()
  const navigate = useNavigate()
  const active = activeKey(location.pathname)
  const activeTab = useMemo(() => tabs.find(tab => tab.key === active) ?? tabs[0], [active])

  return (
    <PrototypePage>
      <PrototypeTabs
        ariaLabel="风控中心页签"
        activeKey={active}
        onChange={(key) => {
          const tab = tabs.find(item => item.key === key)
          if (tab) navigate(tab.path)
        }}
        items={tabs.map((tab, index) => ({ key: tab.key, label: tab.label, subLabel: tab.subLabel, number: String(index + 1).padStart(2, '0') }))}
      />
      <PrototypePageHeader
        title={`风控中心 - ${activeTab.label}`}
        subtitle="订单前置拦截 · 持仓暴露 · 策略回撤 · 事件审计"
        actions={[
          { key: 'paper', label: '模拟盘风控', active: true },
          { key: 'live', label: '实盘强制预检', tone: 'warn' },
          { key: 'audit', label: '全链路留痕', tone: 'neutral' },
        ]}
      />
      <P0WorkflowNav currentStep="risk" />

      <div className="kpis">
        <MetricCard label="今日拦截" value="2" sub="需人工复核 1 笔" tone="warn" />
        <MetricCard label="风险通过率" value="96%" sub="模拟盘订单" tone="up" />
        <MetricCard label="最大集中度" value="18%" sub="半导体设备" tone="accent" />
        <MetricCard label="审计留痕" value="128" sub="近 7 日" tone="muted" />
      </div>

      {active === 'dashboard' && (
        <div className="row r-6-4">
          <PrototypeCard title="风控闸门概览" icon={<SafetyCertificateOutlined />} meta="Risk Gate">
            <table className="tbl">
              <thead><tr><th>规则</th><th>作用域</th><th>结果</th><th className="r">说明</th></tr></thead>
              <tbody>
                <tr><td className="nm">资金充足</td><td>Order</td><td className="up">pass</td><td className="r">模拟盘资金足够</td></tr>
                <tr><td className="nm">仓位上限</td><td>Plan</td><td className="warn">warn</td><td className="r">半导体集中度接近阈值</td></tr>
                <tr><td className="nm">实盘券商</td><td>Broker</td><td className="down">locked</td><td className="r">QMT 未人工放行</td></tr>
              </tbody>
            </table>
          </PrototypeCard>
          <SideRail title="闸门结论" meta="Order Gate">
            <DataDomainBadge domain="account" label="账户级风控" />
            <RiskBanner status="warn" title="实盘保持锁定" detail="所有实盘订单必须经过券商连接、风控判定和人工确认。" />
          </SideRail>
        </div>
      )}

      {active === 'overview' && (
        <PrototypeCard title="组合风险暴露" icon={<AlertOutlined />} meta="Portfolio">
          {[
            ['半导体', 18, 'var(--warn)'],
            ['新能源', 14, 'var(--accent)'],
            ['单票最大仓位', 12, 'var(--down)'],
            ['现金缓冲', 32, 'var(--up)'],
          ].map(([label, value, color]) => (
            <div className="dim-row" key={String(label)}>
              <div className="dim-lbl">{label}</div>
              <div className="dim-bar-wrap"><div className="dim-bar" style={{ width: `${Number(value) * 3}%`, background: String(color) }} /></div>
              <div className="dim-val">{value}%</div>
            </div>
          ))}
        </PrototypeCard>
      )}

      {active === 'positions' && (
        <PrototypeCard title="持仓风险" icon={<SafetyCertificateOutlined />} meta="Position">
          <table className="tbl">
            <thead><tr><th>标的</th><th>风险</th><th className="r">仓位</th><th className="r">动作</th></tr></thead>
            <tbody>
              <tr><td className="nm">300750 宁德时代</td><td>波动扩大</td><td className="r mono">12%</td><td className="r">降低追价</td></tr>
              <tr><td className="nm">688981 中芯国际</td><td>主题拥挤</td><td className="r mono">9%</td><td className="r">人工复核</td></tr>
            </tbody>
          </table>
        </PrototypeCard>
      )}

      {active === 'strategies' && (
        <PrototypeCard title="策略风险" icon={<SafetyCertificateOutlined />} meta="Strategy">
          <table className="tbl">
            <thead><tr><th>方案</th><th>风险项</th><th className="r">回撤</th><th className="r">状态</th></tr></thead>
            <tbody>
              <tr><td className="nm">半导体竞价共振</td><td>高开回落</td><td className="r down">-4.2%</td><td className="r warn">需复核</td></tr>
              <tr><td className="nm">价值回撤低吸</td><td>流动性一般</td><td className="r down">-2.1%</td><td className="r up">通过</td></tr>
            </tbody>
          </table>
        </PrototypeCard>
      )}

      {active === 'market' && (
        <PrototypeCard title="市场风险事件" icon={<AlertOutlined />} meta="Market">
          <div className="row r-3">
            {['指数高开回落', '半导体拥挤度上升', '北向资金波动'].map(item => (
              <div className="prototype-fallback" key={item}>{item}</div>
            ))}
          </div>
        </PrototypeCard>
      )}

      {active === 'audit' && (
        <div className="row r-6-4">
          <PrototypeCard title="RiskVerdict 审计" icon={<AuditOutlined />} meta="Order / Context">
            <table className="tbl">
              <thead><tr><th>RiskVerdict</th><th>Order</th><th>DecisionContext</th><th>结果</th><th className="r">规则</th></tr></thead>
              <tbody>
                {auditRows.map(row => (
                  <tr key={row.verdict}>
                    <td className="code">{row.verdict}</td>
                    <td className="code">{row.order}</td>
                    <td className="code">{row.context}</td>
                    <td className={row.result === 'pass' ? 'up' : row.result === 'warn' ? 'warn' : 'down'}>{row.result}</td>
                    <td className="r">{row.rule}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </PrototypeCard>
          <SideRail title="审计链路" meta="不可绕过">
            <LineageChips
              items={[
                { label: '订单', value: 'ORD-*' },
                { label: '风控', value: 'RV-*', tone: 'warn' },
                { label: '上下文', value: 'CTX-*', tone: 'accent' },
              ]}
            />
            <RiskBanner status="pass" title="留痕完整" detail="每次通过、警告、拒绝和人工复核都保留可追溯上下文。" />
          </SideRail>
        </div>
      )}
    </PrototypePage>
  )
}
