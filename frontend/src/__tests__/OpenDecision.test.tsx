import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import OpenDecision from '../pages/OpenDecision'

function renderOpenDecision(route = '/open-decision') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <OpenDecision />
    </MemoryRouter>,
  )
}

function expectPrototypeText(label: string) {
  expect(screen.getAllByText(label, { exact: false }).length).toBeGreaterThan(0)
}

describe('OpenDecision prototype pages', () => {
  it.each([
    [
      '/open-decision',
      ['距竞价数据采集', '隔夜新闻', '昨日复盘', '候选池预加载', '昨日强势板块 (可能延续)'],
    ],
    [
      '/open-decision/auction',
      ['竞价分析引擎', '竞价意图全景', '抢筹 TOP 10', '出货预警 TOP 10', '竞价选股引擎', '可转债竞价', '全量竞价明细', '候选池预览'],
    ],
    [
      '/open-decision/signals',
      ['验证工作台 · 逐条确认信号 · Kronos 交叉验证 · 一键推送候选池', '批量确认买入信号', 'Kronos 30日预测', '风险检查', '一键推送已确认'],
    ],
    [
      '/open-decision/candidates',
      ['P0 主链路', '多源候选池', '风控排查', '交易方案预览', '风控预检'],
    ],
    [
      '/open-decision/execution',
      ['总资产', '今日订单', '持仓', '自动交易策略', '今日方案', '需关注'],
    ],
  ])('renders prototype-critical content for %s', (route, labels) => {
    renderOpenDecision(route)

    labels.forEach(label => {
      expectPrototypeText(label)
    })
  })

  it('renders auction analysis with actual candidate and sector panels', () => {
    renderOpenDecision('/open-decision/auction')

    expect(screen.getByRole('heading', { name: '开盘决策 - 竞价分析' })).toBeInTheDocument()
    expect(screen.getByText('抢筹 TOP 10')).toBeInTheDocument()
    expect(screen.getByText('板块共振详情')).toBeInTheDocument()
    expect(screen.getByText('已锁定板块')).toBeInTheDocument()
    expect(screen.getAllByText('宁德时代').length).toBeGreaterThan(0)
  })

  it('matches the auction prototype workbench hierarchy', () => {
    renderOpenDecision('/open-decision/auction')

    expect(screen.getByText('竞价风险提示 · 高开过热板块需二次确认')).toBeInTheDocument()
    expect(screen.getByText('最近刷新 09:25:42')).toBeInTheDocument()
    expect(screen.getByText('中性观察')).toBeInTheDocument()
    expect(screen.getByText('四维评分')).toBeInTheDocument()
    expect(screen.getByText('工作流引导')).toBeInTheDocument()
    expect(screen.getByText('锁定强势板块 -> 切换到竞价选股引擎')).toBeInTheDocument()
  })

  it('matches the signal scan verification workbench prototype', () => {
    renderOpenDecision('/open-decision/signals')

    expect(screen.getByText('锁定板块:')).toBeInTheDocument()
    expect(screen.getByText('仅自选')).toBeInTheDocument()
    expect(screen.getByText('排序:')).toBeInTheDocument()
    expect(screen.getByText('逐条确认决策')).toBeInTheDocument()
    expect(screen.getByText('选中股票')).toBeInTheDocument()
    expect(screen.getByText('六维评分')).toBeInTheDocument()
    expect(screen.getByText('决策分类')).toBeInTheDocument()
    expect(screen.getByText('一键推送已确认 -> 候选池')).toBeInTheDocument()
  })

  it('renders overnight news as a market news feed instead of a numbered task list', () => {
    renderOpenDecision('/open-decision')

    expect(screen.getByText('中芯国际: 收到证监会立案调查通知书')).toBeInTheDocument()
    expect(screen.getAllByText('公告').length).toBeGreaterThan(0)
    expect(screen.getByText('外盘')).toBeInTheDocument()
    expect(screen.getByText('昨 20:35')).toBeInTheDocument()
    expect(screen.getByText('全部还原 LLM原始结果')).toBeInTheDocument()
  })

  it('switches to candidate pool without falling back to a placeholder', () => {
    renderOpenDecision('/open-decision')

    fireEvent.click(screen.getByRole('tab', { name: /候选池/ }))
    expect(screen.getByRole('heading', { name: '开盘决策 - 候选池' })).toBeInTheDocument()
    expectPrototypeText('Candidate 对象预览')
  })
})
