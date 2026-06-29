import { useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  AlertOutlined,
  BarChartOutlined,
  FundProjectionScreenOutlined,
  RadarChartOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import {
  DataDomainBadge,
  LineageChips,
  MetricCard,
  PrototypeCard,
  PrototypePage,
  PrototypePageHeader,
  PrototypeTabs,
  RiskBanner,
  SegmentTabs,
  SideRail,
} from '../components/prototype'

const tabs = [
  { key: 'entry', path: '/diagnosis', label: '诊断入口', subLabel: '搜索标的' },
  { key: 'overview', path: '/diagnosis/overview', label: '综合诊断', subLabel: '维度评分' },
  { key: 'model', path: '/diagnosis/model', label: '模型视角', subLabel: 'Kronos / 因子' },
  { key: 'compare', path: '/diagnosis/compare', label: '多股对比', subLabel: '横向比较' },
  { key: 'risk', path: '/diagnosis/risk', label: '风险扫描', subLabel: '操作建议' },
]

const dimensionRows = [
  { name: '技术面', score: 88, note: '趋势向上 · 量价共振', color: 'var(--accent)' },
  { name: '资金面', score: 76, note: '主力净流入连续 3 日', color: 'var(--warn)' },
  { name: '基本面', score: 72, note: '估值略高 · 利润改善', color: 'var(--down)' },
  { name: '模型面', score: 84, note: 'Kronos 30日路径偏强', color: 'var(--accent)' },
  { name: '情绪面', score: 79, note: '板块关注度提升', color: 'var(--up)' },
]

const compareRows = [
  ['300750', '宁德时代', '86', '强势', '资金面领先'],
  ['688981', '中芯国际', '78', '震荡', '模型面回升'],
  ['600519', '贵州茅台', '73', '防御', '估值安全边际高'],
]

function activeTabFromPath(pathname: string) {
  if (pathname.includes('/overview')) return 'overview'
  if (pathname.includes('/model')) return 'model'
  if (pathname.includes('/compare')) return 'compare'
  if (pathname.includes('/risk')) return 'risk'
  return 'entry'
}

export default function Diagnosis() {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const active = activeTabFromPath(pathname)
  const [period, setPeriod] = useState('today')
  const tab = useMemo(() => tabs.find(item => item.key === active) ?? tabs[0], [active])

  return (
    <PrototypePage>
      <PrototypeTabs
        items={tabs}
        activeKey={active}
        ariaLabel="个股诊断模块页签"
        onChange={key => navigate(tabs.find(item => item.key === key)?.path ?? '/diagnosis')}
      />

      <PrototypePageHeader
        title={`个股诊断 - ${tab.label}`}
        subtitle="单股画像 · 五维评分 · 模型解释 · 风险动作建议"
        actions={[
          { key: 'scope', label: '私有诊断', active: true, tone: 'neutral' },
          { key: 'source', label: '公共行情 + 账户持仓', tone: 'up' },
        ]}
      />

      <div className="kpis">
        <MetricCard label="诊断标的" value="300750" sub="宁德时代" tone="accent" />
        <MetricCard label="综合评分" value="82" sub="强势偏多" tone="up" />
        <MetricCard label="风险项" value="3" sub="估值 / 事件 / 集中度" tone="warn" />
        <MetricCard label="报告状态" value="PDF" sub="可生成审计版" tone="muted" />
      </div>

      <div className="r r-2-1">
        <PrototypeCard
          title={active === 'entry' ? '诊断入口' : active === 'compare' ? '多股对比' : active === 'risk' ? '风险扫描' : '五维评分'}
          icon={active === 'risk' ? <AlertOutlined /> : <RadarChartOutlined />}
          meta={<DataDomainBadge domain="user" label="user-scoped" />}
        >
          {active === 'entry' && (
            <>
              <div className="filter-bar">
                <div className="search">
                  <SearchOutlined />
                  <input className="inp" defaultValue="300750 宁德时代" aria-label="诊断标的" />
                </div>
                <button type="button" className="btn primary">开始诊断</button>
                <button type="button" className="btn ghost">导出报告</button>
              </div>
              <LineageChips
                items={[
                  { label: 'Prediction', value: 'Kronos V2.3', tone: 'safe' },
                  { label: 'Signal', value: '强买 82', tone: 'warn' },
                  { label: 'RiskVerdict', value: 'REVIEW', tone: 'accent' },
                ]}
              />
              <div className="prototype-panel-note" style={{ marginTop: 12 }}>
                诊断入口聚合公共行情、模型预测、交易信号和账户持仓，只保存用户自己的诊断历史与导出报告。
              </div>
            </>
          )}

          {(active === 'overview' || active === 'model') && (
            <>
              <SegmentTabs
                items={[
                  { key: 'today', label: '今日' },
                  { key: '30d', label: '近30日' },
                  { key: 'position', label: '持仓口径' },
                ]}
                activeKey={period}
                ariaLabel="诊断周期"
                onChange={setPeriod}
              />
              <div style={{ marginTop: 16 }}>
                {dimensionRows.map(row => (
                  <div className="dim-row" key={row.name} style={{ marginBottom: 10 }}>
                    <div className="dim-lbl">{row.name}<span>{row.note}</span></div>
                    <div className="dim-bar-wrap">
                      <div className="dim-bar" style={{ width: `${row.score}%`, background: row.color }} />
                    </div>
                    <div className="dim-val">{row.score}</div>
                  </div>
                ))}
              </div>
              {active === 'model' && (
                <RiskBanner
                  status="review"
                  title="模型解释：趋势路径偏强，但估值维度拉低总分"
                  detail="Kronos 路径贡献 34%，资金因子贡献 21%，事件风险贡献 -9%。"
                />
              )}
            </>
          )}

          {active === 'compare' && (
            <table className="tbl">
              <thead>
                <tr>
                  <th>代码</th>
                  <th>名称</th>
                  <th className="r">评分</th>
                  <th>状态</th>
                  <th>主要差异</th>
                </tr>
              </thead>
              <tbody>
                {compareRows.map(row => (
                  <tr key={row[0]}>
                    <td className="mono">{row[0]}</td>
                    <td className="nm">{row[1]}</td>
                    <td className="r up">{row[2]}</td>
                    <td>{row[3]}</td>
                    <td>{row[4]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {active === 'risk' && (
            <div style={{ display: 'grid', gap: 12 }}>
              <RiskBanner status="warn" title="操作建议：减仓观察" detail="触发估值分位过高、板块波动扩大、单票集中度偏高。" />
              <table className="tbl">
                <thead>
                  <tr>
                    <th>风险项</th>
                    <th>等级</th>
                    <th>动作</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    ['估值分位', '中', '等待回落至 70% 分位以下'],
                    ['事件风险', '中', '财报窗口前降低仓位'],
                    ['账户集中度', '高', '单票不超过账户净值 12%'],
                  ].map(row => (
                    <tr key={row[0]}>
                      <td>{row[0]}</td>
                      <td className={row[1] === '高' ? 'up' : ''}>{row[1]}</td>
                      <td>{row[2]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </PrototypeCard>

        <SideRail title="诊断联动" meta="Prediction / Signal">
          <PrototypeCard title="模型概览" icon={<FundProjectionScreenOutlined />}>
            <div className="li-row">
              <div className="li-badge">K</div>
              <div className="li-main">
                <div className="n">30日目标价 242.30</div>
                <div className="s">置信度 78% · 上行空间 +12.5%</div>
              </div>
            </div>
            <div className="li-row">
              <div className="li-badge">S</div>
              <div className="li-main">
                <div className="n">信号强买 82</div>
                <div className="s">技术面与资金面共振</div>
              </div>
            </div>
          </PrototypeCard>
          <PrototypeCard title="报告输出" icon={<BarChartOutlined />}>
            <div className="prototype-panel-note">生成报告时写入 DecisionContext、模型版本、数据时点和账户口径，便于复盘。</div>
          </PrototypeCard>
        </SideRail>
      </div>
    </PrototypePage>
  )
}
