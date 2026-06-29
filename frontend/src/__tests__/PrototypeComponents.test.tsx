import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  DataFreshnessBar,
  DataDomainBadge,
  EmptyState,
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

describe('prototype shared components', () => {
  it('renders page header actions without platform explainer copy', () => {
    render(
      <PrototypePage>
        <PrototypePageHeader
          title="市场情绪"
          subtitle="八维风向感知模型"
          actions={[{ key: 'hot', label: '过热(80+)', tone: 'neutral' }]}
        />
      </PrototypePage>,
    )

    expect(screen.getByRole('heading', { name: '市场情绪' })).toBeInTheDocument()
    expect(screen.getByText('八维风向感知模型')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '过热(80+)' })).toBeInTheDocument()
    expect(screen.queryByText('公共+私有隔离')).not.toBeInTheDocument()
  })

  it('renders page header data freshness so users know which date is loaded', () => {
    render(
      <PrototypePage>
        <PrototypePageHeader
          title="竞价意图"
          subtitle="四维评分模型"
          dataFreshness={(
            <DataFreshnessBar
              tradeDate="2026-06-25"
              updatedAt="2026-06-25T09:25:42+08:00"
              source="dashboard/auction"
            />
          )}
        />
      </PrototypePage>,
    )

    expect(screen.getByText('交易日：2026-06-25')).toBeInTheDocument()
    expect(screen.getByText('数据更新：09:25:42')).toBeInTheDocument()
    expect(screen.getByText('来源：dashboard/auction')).toBeInTheDocument()
  })

  it('makes missing backend trade date explicit', () => {
    render(<DataFreshnessBar updatedAt="2026-06-25T10:30:00+08:00" source="prediction-service" />)

    expect(screen.getByText('交易日：后端未返回数据日期')).toBeInTheDocument()
    expect(screen.getByText('来源：prediction-service')).toBeInTheDocument()
  })

  it('renders navigable prototype tabs', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()

    render(
      <PrototypeTabs
        ariaLabel="智能看板页签"
        activeKey="sentiment"
        onChange={onChange}
        items={[
          { key: 'sentiment', label: '市场情绪', subLabel: '宽度 / 资金' },
          { key: 'auction', label: '竞价意图', subLabel: '9:25 抢筹' },
        ]}
      />,
    )

    expect(screen.getByRole('tab', { name: /市场情绪/ })).toHaveAttribute('aria-current', 'page')
    await user.click(screen.getByRole('tab', { name: /竞价意图/ }))
    expect(onChange).toHaveBeenCalledWith('auction')
  })

  it('renders segment tabs and metric cards in preview vocabulary', () => {
    render(
      <>
        <SegmentTabs
          ariaLabel="预测周期"
          activeKey="all"
          onChange={vi.fn()}
          items={[
            { key: 'all', label: '全部' },
            { key: '30d', label: '预测30日', count: '30' },
          ]}
        />
        <PrototypeCard title="市场快照" meta="基于 3,852 只股票">
          <MetricCard label="涨停" value="87" sub="+12 vs 昨" tone="up" />
        </PrototypeCard>
      </>,
    )

    expect(screen.getByRole('tab', { name: '全部' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('市场快照')).toBeInTheDocument()
    expect(screen.getByText('涨停')).toBeInTheDocument()
    expect(screen.getByText('87')).toBeInTheDocument()
  })

  it('renders shared page primitives for data domain, lineage, risk and fallback states', () => {
    render(
      <SideRail title="交易准备" meta="账户私有">
        <DataDomainBadge domain="account" label="账户私有" />
        <LineageChips
          items={[
            { label: '候选', value: 'CAND-001' },
            { label: '方案', value: 'PLAN-001' },
            { label: '风控', value: 'RV-001', tone: 'warn' },
          ]}
        />
        <RiskBanner status="warn" title="需要复核" detail="实盘前必须完成风控确认" />
        <EmptyState title="等待真实数据" detail="接口接入后会显示持仓和订单状态" actionLabel="刷新" />
      </SideRail>,
    )

    expect(screen.getByText('交易准备')).toBeInTheDocument()
    expect(screen.getAllByText('账户私有')).toHaveLength(2)
    expect(screen.getByText('CAND-001')).toBeInTheDocument()
    expect(screen.getByText('PLAN-001')).toBeInTheDocument()
    expect(screen.getByText('RV-001')).toBeInTheDocument()
    expect(screen.getByText('需要复核')).toBeInTheDocument()
    expect(screen.getByText('等待真实数据')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '刷新' })).toBeInTheDocument()
  })
})
