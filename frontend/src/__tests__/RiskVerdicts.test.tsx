import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ConfigProvider, App as AntdApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import RiskVerdicts from '../pages/RiskVerdicts'

const mocks = vi.hoisted(() => ({
  getRiskVerdicts: vi.fn(),
}))

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return {
    ...actual,
    tradeApi: {
      ...actual.tradeApi,
      getRiskVerdicts: mocks.getRiskVerdicts,
    },
  }
})

function renderRiskVerdicts(initialEntries = ['/trade/risk-verdicts']) {
  return render(
    <ConfigProvider locale={zhCN}>
      <AntdApp>
        <MemoryRouter initialEntries={initialEntries}>
          <Routes>
            <Route path="/trade/risk-verdicts" element={<RiskVerdicts />} />
            <Route path="/trade/decision-contexts" element={<div>决策上下文页</div>} />
          </Routes>
        </MemoryRouter>
      </AntdApp>
    </ConfigProvider>,
  )
}

describe('RiskVerdicts 风控闸门', () => {
  beforeEach(() => {
    mocks.getRiskVerdicts.mockReset()
    mocks.getRiskVerdicts.mockResolvedValue({
      data: {
        total: 1,
        page: 1,
        page_size: 20,
        records: [
          {
            id: 1,
            verdict_id: 'RV-1',
            tenant_id: 'tenant-alpha',
            owner_user_id: '7',
            account_id: 'paper-u7',
            result: 'reject',
            scope: 'order',
            trade_mode: 'paper',
            symbol: '300750',
            order_id: 'ORD-1',
            plan_id: 'PLAN-1',
            candidate_id: 'CAND-1',
            decision_context_id: 'CTX-1',
            created_at: '2026-06-27T10:30:00Z',
            details: {
              verdict_id: 'RV-1',
              result: 'reject',
              risk_check: {
                passed: false,
                checks: [
                  { rule: '资金充足', level: 'reject', message: '资金不足' },
                  { rule: '仓位上限', level: 'pass', message: '' },
                ],
              },
            },
          },
        ],
      },
    })
  })

  it('加载风控判定历史并展示规则级详情', async () => {
    renderRiskVerdicts()

    expect((await screen.findAllByText('风控闸门')).length).toBeGreaterThan(0)
    await waitFor(() => {
      expect(mocks.getRiskVerdicts).toHaveBeenCalledWith({ page: 1, page_size: 20 })
    })

    expect(screen.getByText('RV-1')).toBeInTheDocument()
    expect(screen.getByText('300750')).toBeInTheDocument()
    expect(screen.getByText('PLAN-1')).toBeInTheDocument()
    expect(screen.getByText('资金充足')).toBeInTheDocument()
    expect(screen.getByText('资金不足')).toBeInTheDocument()
    expect(screen.getByText('仓位上限')).toBeInTheDocument()
  })

  it('从 URL 读取 lineage 条件并可跳转到决策上下文', async () => {
    const user = userEvent.setup()
    renderRiskVerdicts(['/trade/risk-verdicts?decision_context_id=CTX-1&order_id=ORD-1&plan_id=PLAN-1&candidate_id=CAND-1&code=300750'])

    await waitFor(() => {
      expect(mocks.getRiskVerdicts).toHaveBeenCalledWith({
        page: 1,
        page_size: 20,
        decision_context_id: 'CTX-1',
        order_id: 'ORD-1',
        plan_id: 'PLAN-1',
        candidate_id: 'CAND-1',
        code: '300750',
      })
    })

    await user.click(await screen.findByRole('button', { name: '决策上下文' }))

    expect(screen.getByText('决策上下文页')).toBeInTheDocument()
  })
})
