import { render, screen, within } from '@testing-library/react'
import { ConfigProvider, App as AntdApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Screener from '../pages/Screener'
import Strategy from '../pages/Strategy'

vi.mock('../api/client', () => {
  const api = {
    get: vi.fn((url: string) => {
      if (url === '/strategy/templates') return Promise.resolve({ data: { templates: [] } })
      if (url === '/strategy/plans') return Promise.resolve({ data: { plans: [] } })
      return Promise.resolve({ data: {} })
    }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    delete: vi.fn().mockResolvedValue({ data: {} }),
  }
  return {
    default: api,
    screenerApi: {
      getModes: vi.fn().mockResolvedValue({ data: { modes: [] } }),
      run: vi.fn().mockResolvedValue({ data: { picks: [] } }),
    },
    strategyApi: {
      createPlan: vi.fn().mockResolvedValue({ data: { plan: { id: 'PLAN-1' } } }),
      addPicks: vi.fn().mockResolvedValue({ data: {} }),
    },
    backtestApi: {
      run: vi.fn().mockResolvedValue({ data: { status: 'ok' } }),
    },
  }
})

function renderRoutes(initialRoute: string) {
  render(
    <ConfigProvider locale={zhCN}>
      <AntdApp>
        <MemoryRouter initialEntries={[initialRoute]}>
          <Routes>
            <Route path="/screener" element={<Screener />} />
            <Route path="/strategy" element={<Strategy />} />
          </Routes>
        </MemoryRouter>
      </AntdApp>
    </ConfigProvider>,
  )
}

describe('P0 workflow page integration', () => {
  it('keeps screener aligned to the 3.1 workbench prototype instead of showing the P0 rail', async () => {
    renderRoutes('/screener')

    expect(await screen.findByLabelText('模型分类页签')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /加入候选池 →/ })).toBeInTheDocument()
    expect(screen.queryByLabelText('P0 主链路')).not.toBeInTheDocument()
  })

  it('shows plan step on the strategy page', async () => {
    renderRoutes('/strategy')

    const nav = await screen.findByLabelText('P0 主链路')
    expect(within(nav).getByRole('button', { name: /方案管理/ })).toHaveAttribute('aria-current', 'step')
    expect(within(nav).getByRole('button', { name: /风控闸门/ })).toBeInTheDocument()
    expect(within(nav).getByRole('button', { name: /回测复盘/ })).toBeInTheDocument()
  })
})
