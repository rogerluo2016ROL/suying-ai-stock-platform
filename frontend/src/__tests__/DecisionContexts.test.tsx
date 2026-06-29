import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ConfigProvider, App as AntdApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import DecisionContexts from '../pages/DecisionContexts'

const mocks = vi.hoisted(() => ({
  getDecisionContexts: vi.fn(),
}))

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return {
    ...actual,
    tradeApi: {
      ...actual.tradeApi,
      getDecisionContexts: mocks.getDecisionContexts,
    },
  }
})

function renderDecisionContexts(initialEntries = ['/trade/decision-contexts?decision_context_id=CTX-1']) {
  return render(
    <ConfigProvider locale={zhCN}>
      <AntdApp>
        <MemoryRouter initialEntries={initialEntries}>
          <Routes>
            <Route path="/trade/decision-contexts" element={<DecisionContexts />} />
            <Route path="/trade/risk-verdicts" element={<div>风控闸门页</div>} />
          </Routes>
        </MemoryRouter>
      </AntdApp>
    </ConfigProvider>,
  )
}

describe('DecisionContexts 决策上下文', () => {
  beforeEach(() => {
    mocks.getDecisionContexts.mockReset()
    mocks.getDecisionContexts.mockResolvedValue({
      data: {
        total: 1,
        page: 1,
        page_size: 20,
        records: [
          {
            id: 1,
            decision_context_id: 'CTX-1',
            tenant_id: 'tenant-alpha',
            owner_user_id: '7',
            account_id: 'paper-u7',
            source_type: 'order',
            symbol: '300750',
            plan_id: 'PLAN-1',
            candidate_id: 'CAND-1',
            intent: 'place_order',
            payload: {
              direction: 'BUY',
              price: 218.5,
              volume: 100,
              reason: '候选池强势突破',
            },
            created_at: '2026-06-27T10:29:30Z',
          },
        ],
      },
    })
  })

  it('按 URL 条件加载决策上下文并可反向查看风控', async () => {
    const user = userEvent.setup()
    renderDecisionContexts(['/trade/decision-contexts?decision_context_id=CTX-1&plan_id=PLAN-1&candidate_id=CAND-1&code=300750'])

    await waitFor(() => {
      expect(mocks.getDecisionContexts).toHaveBeenCalledWith({
        page: 1,
        page_size: 20,
        decision_context_id: 'CTX-1',
        plan_id: 'PLAN-1',
        candidate_id: 'CAND-1',
        code: '300750',
      })
    })

    expect(await screen.findByText('决策上下文')).toBeInTheDocument()
    expect(screen.getByText('CTX-1')).toBeInTheDocument()
    expect(screen.getByText('PLAN-1')).toBeInTheDocument()
    expect(screen.getByText('CAND-1')).toBeInTheDocument()
    expect(screen.getByText(/候选池强势突破/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '关联风控' }))

    expect(screen.getByText('风控闸门页')).toBeInTheDocument()
  })
})
