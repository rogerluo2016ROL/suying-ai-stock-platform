import { ApiOutlined, CheckCircleOutlined, ClockCircleOutlined, DatabaseOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { DataDomainBadge, MetricCard, PrototypeCard, PrototypePage, PrototypePageHeader, RiskBanner, SideRail } from '../components/prototype'

const services = [
  ['api-gateway', '8080', '在线', '统一入口 / 鉴权透传'],
  ['backend-auth', '9001', '在线', 'JWT / RBAC / tenant'],
  ['prediction-service', '8002', '在线', 'Kronos 预测'],
  ['signal-service', '8004', '在线', '交易信号'],
  ['trade-service', '8006', '在线', '模拟盘交易'],
  ['training-service', '8008', '同步中', '训练队列'],
]

export default function RuntimeStatus() {
  return (
    <PrototypePage>
      <PrototypePageHeader
        title="运行状态 - 服务健康"
        subtitle="服务健康 · 数据延迟 · 模型任务 · 交易链路"
        actions={[
          { key: 'admin', label: '管理员视图', active: true, tone: 'neutral' },
          { key: 'paper', label: '实盘默认关闭', tone: 'warn' },
        ]}
      />
      <div className="kpis">
        <MetricCard label="在线服务" value="11/11" sub="UAT 网关可达" tone="up" />
        <MetricCard label="数据延迟" value="12s" sub="行情缓存" tone="accent" />
        <MetricCard label="模型任务" value="3" sub="1 个训练中" tone="warn" />
        <MetricCard label="交易链路" value="Paper" sub="实盘默认关闭" tone="muted" />
      </div>
      <div className="r r-2-1">
        <PrototypeCard
          title="服务健康矩阵"
          icon={<ApiOutlined />}
          meta={<DataDomainBadge domain="public" label="runtime-admin" />}
        >
          <table className="tbl">
            <thead>
              <tr>
                <th>服务</th>
                <th>端口</th>
                <th>状态</th>
                <th>职责</th>
              </tr>
            </thead>
            <tbody>
              {services.map(([name, port, status, duty]) => (
                <tr key={name}>
                  <td className="nm">{name}</td>
                  <td className="mono">{port}</td>
                  <td>
                    {status === '在线'
                      ? <CheckCircleOutlined className="down" />
                      : <ClockCircleOutlined style={{ color: 'var(--warn)' }} />} {status}
                  </td>
                  <td>{duty}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </PrototypeCard>

        <SideRail title="运行闸门" meta="Ops">
          <RiskBanner
            status="pass"
            title="模拟盘链路可用"
            detail="交易服务、风控中心、回测复盘均可在 paper 模式下联动。"
          />
          <PrototypeCard title="数据与模型" icon={<DatabaseOutlined />}>
            <div className="li-row">
              <div className="li-badge">PG</div>
              <div className="li-main">
                <div className="n">PostgreSQL 主库</div>
                <div className="s">公共行情与私有对象分域查询</div>
              </div>
            </div>
            <div className="li-row">
              <div className="li-badge">ML</div>
              <div className="li-main">
                <div className="n">模型服务在线</div>
                <div className="s">预测、信号、诊断输出带模型版本</div>
              </div>
            </div>
          </PrototypeCard>
          <PrototypeCard title="安全状态" icon={<SafetyCertificateOutlined />}>
            <div className="prototype-panel-note">实盘券商通道需要 broker 配置、风控通过、操作审计三项同时满足才可启用。</div>
          </PrototypeCard>
        </SideRail>
      </div>
    </PrototypePage>
  )
}
