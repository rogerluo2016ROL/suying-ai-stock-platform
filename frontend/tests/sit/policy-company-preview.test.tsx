import { cleanup, render, waitFor } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { MemoryRouter } from 'react-router-dom'
import SupplyChainBom from '../../src/pages/SupplyChainBom'

// SIT scope：SupplyChainBom 4.1 policy-analysis + 4.3 company-analysis tab 渲染 + 缺数据兜底。
// 补建 follow-up（dev-5 #27 429 failed，PL 接手代码 tsc0+16 unit 绿，sit 缺，reviewer-2 建议补）。
// 最小 integration：mock api 返空 → render policy/company tab → 断言不崩 + 缺数据兜底不空白。

vi.mock('echarts-for-react', () => ({ default: () => <div data-testid="echart" /> }))
vi.mock('echarts', () => ({
  init: vi.fn(() => ({ setOption: vi.fn(), on: vi.fn(), resize: vi.fn(), clear: vi.fn(), dispose: vi.fn() })),
}))

vi.mock('../../src/api/client', () => ({
  screenerApi: {
    getSupplyChainThemes: vi.fn().mockResolvedValue({ data: { data: { themes: [] } } }),
    getSupplyChainBom: vi.fn().mockResolvedValue({ data: { data: { tree: null } } }),
    getSupplyChainWorkbench: vi.fn().mockResolvedValue({ data: { data: {} } }),
    getSupplyChainNode: vi.fn().mockResolvedValue({ data: { data: null } }),
    getSupplyChainCompany: vi.fn().mockResolvedValue({ data: { data: { companies: [] } } }),
    getSupplyChainMappingQuality: vi.fn().mockResolvedValue({ data: { data: {} } }),
    getSupplyChainMappingReviewQueue: vi.fn().mockResolvedValue({ data: { data: [] } }),
    reviewSupplyChainMapping: vi.fn(),
    extractSupplyChainFacts: vi.fn(),
  },
  chainApi: {
    interpretPolicy: vi.fn().mockResolvedValue({ data: { data: null } }),
    deconstructChain: vi.fn().mockResolvedValue({ data: { data: { tree: null } } }),
    getNodeCompanies: vi.fn().mockResolvedValue({ data: { data: [] } }),
    getCandidates: vi.fn().mockResolvedValue({ data: { data: [] } }),
  },
}))

const renderAt = (path: string) =>
  render(
    <ConfigProvider locale={zhCN}>
      <MemoryRouter initialEntries={[path]}>
        <SupplyChainBom />
      </MemoryRouter>
    </ConfigProvider>
  )

describe('SupplyChainBom 4.1 policy + 4.3 company SIT（#27 补）', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('4.1 policy tab 渲染不崩 + 缺数据兜底（policyResult null 不空白）', async () => {
    const { container } = renderAt('/supply-chain-bom/policy')
    await waitFor(() => expect(container.firstChild).toBeTruthy())
    // policy tab 渲染即验证 mock 链路通 + 缺数据不崩
    expect(container.textContent).toMatch(/政策|产业链|梳理|policy/i)
  })

  it('4.3 company tab 渲染不崩 + 缺数据兜底（companies 空不空白）', async () => {
    const { container } = renderAt('/supply-chain-bom/company')
    await waitFor(() => expect(container.firstChild).toBeTruthy())
    expect(container.textContent).toMatch(/公司|多维度|对比|分析|产业链/i)
  })

  it('4.1 policy tab 切换到 4.3 company 不崩（tab 路由切换稳定）', async () => {
    const { container, rerender } = renderAt('/supply-chain-bom/policy')
    await waitFor(() => expect(container.firstChild).toBeTruthy())
    rerender(
      <ConfigProvider locale={zhCN}>
        <MemoryRouter initialEntries={['/supply-chain-bom/company']}>
          <SupplyChainBom />
        </MemoryRouter>
      </ConfigProvider>
    )
    await waitFor(() => expect(container.firstChild).toBeTruthy())
    expect(container.textContent).toMatch(/公司|产业链/i)
  })
})
