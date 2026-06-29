import { ApartmentOutlined, CloudServerOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
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

export default function PlatformUpgrade() {
  return (
    <PrototypePage>
      <PrototypePageHeader
        title="平台升级 - 云端多租户"
        subtitle="多租户 · 公私数据隔离 · 云端部署 · 券商适配"
        actions={[
          { key: 'tenant', label: 'tenant/user/account', active: true, tone: 'neutral' },
          { key: 'broker', label: 'QMT 沙箱优先', tone: 'warn' },
        ]}
      />
      <div className="kpis">
        <MetricCard label="账号隔离" value="已启用" sub="私有对象强归属" tone="accent" />
        <MetricCard label="公共数据" value="shared" sub="行情 / 模型 / 因子" tone="up" />
        <MetricCard label="券商模式" value="Paper" sub="QMT 沙箱待启用" tone="warn" />
        <MetricCard label="云端基线" value="Ready" sub="网关 + 服务拆分" tone="muted" />
      </div>
      <div className="r r-2-1">
        <PrototypeCard
          title="多租户升级矩阵"
          icon={<ApartmentOutlined />}
          meta={<DataDomainBadge domain="tenant" label="platform-governance" />}
        >
          <table className="tbl">
            <thead>
              <tr>
                <th>能力</th>
                <th>当前状态</th>
                <th>落地要求</th>
                <th>验收口径</th>
              </tr>
            </thead>
            <tbody>
              {[
                ['公共行情', '共享', '只读共享缓存', '不同账号看到同一行情时点'],
                ['自选/方案', '私有', 'tenant_id + owner_user_id', '跨账户不可见'],
                ['交易账户', '账户级', 'account_id 强绑定', '订单必须绑定账户'],
                ['券商通道', '沙箱', 'broker_mode + risk gate', '实盘默认锁定'],
                ['云端部署', '可迁移', '网关统一鉴权', '服务可水平扩展'],
              ].map(row => (
                <tr key={row[0]}>
                  <td className="nm">{row[0]}</td>
                  <td>{row[1]}</td>
                  <td>{row[2]}</td>
                  <td>{row[3]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </PrototypeCard>

        <SideRail title="治理边界" meta="Cloud">
          <RiskBanner
            status="review"
            title="公共数据 / 私有对象边界"
            detail="行情、因子、模型版本共享；自选、候选池、方案、订单、风控判定按租户/用户/账户隔离。"
          />
          <PrototypeCard title="迁移链路" icon={<CloudServerOutlined />}>
            <LineageChips
              items={[
                { label: 'Auth', value: 'RBAC', tone: 'accent' },
                { label: 'Data', value: 'shared', tone: 'safe' },
                { label: 'Trade', value: 'paper-first', tone: 'warn' },
              ]}
            />
            <div className="prototype-panel-note" style={{ marginTop: 10 }}>
              前端上下文负责传递 tenant/user/account/trade_mode，后端服务按字段做强过滤。
            </div>
          </PrototypeCard>
          <PrototypeCard title="券商接入" icon={<SafetyCertificateOutlined />}>
            <div className="prototype-panel-note">Xtquant QMT 先接模拟盘和沙箱账户，其他券商通过 BrokerInterface 扩展，实盘必须保留人工确认与审计。</div>
          </PrototypeCard>
        </SideRail>
      </div>
    </PrototypePage>
  )
}
