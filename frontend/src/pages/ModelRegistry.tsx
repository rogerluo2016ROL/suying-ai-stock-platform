import { ApiOutlined, CheckCircleOutlined, RollbackOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
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
  { key: 'registry', label: '版本治理', subLabel: '生产 / 候选 / 回滚' },
]

const registryRows = [
  ['kronos-path-v2.3', 'K线预测', 'production', 'IC 0.12', '2026-06-27 21:10'],
  ['signal-rank-lgbm-v1.8', '交易信号', 'candidate', '命中率 68%', '2026-06-28 09:32'],
  ['diagnosis-risk-v1.2', '个股诊断', 'staging', '风险召回 81%', '2026-06-27 18:20'],
  ['kronos-path-v2.2', 'K线预测', 'rollback', 'IC 0.09', '2026-06-18 20:05'],
]

function stageLabel(stage: string) {
  if (stage === 'production') return '生产'
  if (stage === 'candidate') return '候选'
  if (stage === 'staging') return '灰度'
  return '回滚点'
}

export default function ModelRegistry() {
  return (
    <PrototypePage>
      <PrototypeTabs
        items={tabs}
        activeKey="registry"
        ariaLabel="模型注册模块页签"
        onChange={() => undefined}
      />

      <PrototypePageHeader
        title="模型注册 - 版本治理"
        subtitle="模型列表 · 指标对比 · 部署阶段 · 审计记录"
        actions={[
          { key: 'admin', label: '管理员', active: true, tone: 'neutral' },
          { key: 'rollback', label: '回滚可用', tone: 'up' },
        ]}
      />

      <div className="kpis">
        <MetricCard label="已注册" value="12" sub="Kronos / 因子 / 诊断" tone="accent" />
        <MetricCard label="生产版本" value="3" sub="线上服务引用" tone="up" />
        <MetricCard label="候选版本" value="2" sub="等待发布闸门" tone="warn" />
        <MetricCard label="回滚点" value="5" sub="保留 30 天" tone="muted" />
      </div>

      <div className="r r-2-1">
        <PrototypeCard
          title="生产模型注册表"
          icon={<ApiOutlined />}
          meta={<DataDomainBadge domain="public" label="shared-model" />}
        >
          <table className="tbl">
            <thead>
              <tr>
                <th>模型版本</th>
                <th>用途</th>
                <th>阶段</th>
                <th>关键指标</th>
                <th>更新时间</th>
              </tr>
            </thead>
            <tbody>
              {registryRows.map(row => (
                <tr key={row[0]}>
                  <td className="mono">{row[0]}</td>
                  <td>{row[1]}</td>
                  <td>{stageLabel(row[2])}</td>
                  <td className={row[2] === 'candidate' ? 'up' : ''}>{row[3]}</td>
                  <td>{row[4]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </PrototypeCard>

        <SideRail title="发布审计" meta="Gate">
          <RiskBanner
            status="review"
            title="候选模型等待审批"
            detail="signal-rank-lgbm-v1.8 需要完成实盘前模拟盘 A/B 和漂移检测。"
          />
          <PrototypeCard title="部署链路" icon={<SafetyCertificateOutlined />}>
            <LineageChips
              items={[
                { label: 'Train', value: 'TRN-20260627-03', tone: 'accent' },
                { label: 'Backtest', value: 'BT-8842', tone: 'safe' },
                { label: 'Gate', value: 'REVIEW', tone: 'warn' },
              ]}
            />
            <div className="prototype-panel-note" style={{ marginTop: 10 }}>
              上线、回滚、灰度切换必须写入审计记录，并保留使用该模型生成的预测与信号链路。
            </div>
          </PrototypeCard>
          <PrototypeCard title="快速动作" icon={<RollbackOutlined />}>
            <button type="button" className="btn sm ghost"><CheckCircleOutlined /> 复核生产版本</button>
            <button type="button" className="btn sm ghost" style={{ marginLeft: 8 }}>打开回滚点</button>
          </PrototypeCard>
        </SideRail>
      </div>
    </PrototypePage>
  )
}
