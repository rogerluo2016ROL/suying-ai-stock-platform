import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { MemoryRouter } from 'react-router-dom'
import SupplyChainBom from '../../src/pages/SupplyChainBom'
import { screenerApi, chainApi } from '../../src/api/client'

// SIT scope：SupplyChainBom Step4 单树视图 + overlay 维度切换渲染 + token 化 + 缺数据 EmptyState。
// API client 走 vi.mock（既有 SupplyChainBom.test.tsx 同款）。

vi.mock('echarts-for-react', () => ({
  // 把 option 透传出来便于断言 mode 专属图表，同时挂 testid 供"渲染了图表"断言
  default: ({ option }: any) => (
    <div
      data-testid={option?.series?.[0]?.type === 'tree' ? 'tree-chart' : 'graph-chart'}
      data-chart-type={option?.series?.[0]?.type}
      data-series-count={option?.series?.length}
    />
  ),
}))

vi.mock('echarts', () => ({
  init: vi.fn(() => ({
    setOption: vi.fn(),
    on: vi.fn(),
    resize: vi.fn(),
    clear: vi.fn(),
    dispose: vi.fn(),
  })),
}))

vi.mock('../../src/api/client', () => ({
  screenerApi: {
    getSupplyChainThemes: vi.fn(),
    getSupplyChainBom: vi.fn(),
    getSupplyChainWorkbench: vi.fn(),
    getSupplyChainNode: vi.fn(),
    getSupplyChainCompany: vi.fn(),
    getSupplyChainMappingQuality: vi.fn(),
    getSupplyChainMappingReviewQueue: vi.fn(),
    reviewSupplyChainMapping: vi.fn(),
    extractSupplyChainFacts: vi.fn(),
  },
  chainApi: {
    interpretPolicy: vi.fn(),
    deconstructChain: vi.fn(),
    getNodeCompanies: vi.fn(),
    getCandidates: vi.fn(),
  },
}))

const themes = [{
  theme_id: 'future_industry_core',
  name: '未来产业主攻方向',
  policy_weight: 1.5,
  keywords: ['量子科技'],
  node_count: 2,
}]

// value_chain 数据：叶子节点带 value_chain 字段，验证 value/competition 图数据源
const chainDeconstructResponse = {
  theme: { id: 'future_industry_core', name: '未来产业主攻方向' },
  view: 'upstream_downstream',
  tree: {
    node_id: 'future_industry_core',
    name: '未来产业主攻方向',
    layer: 1,
    children: [
      {
        node_id: 'quantum_core',
        name: '量子科技',
        layer: 2,
        value_chain: { margin: 38, pricing_power: 62, value_added: 45 },
        children: [],
      },
      {
        node_id: 'embodied_core',
        name: '具身智能',
        layer: 2,
        value_chain: { margin: 25, pricing_power: 48, value_added: 30 },
        children: [],
      },
    ],
  },
}

const workbench = {
  model: { name: '产业链解构选股模型 V4', score_dimensions: [] },
  themes,
  nodes: [],
  edges: [],
  candidates: [],
  node_candidate_companies: [],
  upstream_influence_candidates: [],
  selected_node_thesis: {},
  data_freshness: { market: { latest_trade_date: '2026-06-22' } },
  research_ingestion: { auto_collection_status: 'enabled' },
}

const mappingQuality = { mapping_count: 1, review_queue_count: 0, status_counts: {}, source_counts: {}, hotspot_nodes: [] }
const mappingReviewQueue = { total: 0, limit: 20, offset: 0, items: [] }

function renderSupplyChain(initialRoute = '/supply-chain-bom') {
  return render(
    <ConfigProvider locale={zhCN}>
      <MemoryRouter initialEntries={[initialRoute]}>
        <SupplyChainBom />
      </MemoryRouter>
    </ConfigProvider>,
  )
}

describe('SupplyChainBom Step4 单树 + overlay SIT', () => {
  beforeEach(() => {
    vi.mocked(screenerApi.getSupplyChainThemes).mockResolvedValue({ data: { themes } } as any)
    vi.mocked(screenerApi.getSupplyChainBom).mockResolvedValue({ data: { nodes: [], edges: [] } } as any)
    vi.mocked((screenerApi as any).getSupplyChainWorkbench).mockResolvedValue({ data: workbench })
    vi.mocked((screenerApi as any).getSupplyChainMappingQuality).mockResolvedValue({ data: mappingQuality })
    vi.mocked((screenerApi as any).getSupplyChainMappingReviewQueue).mockResolvedValue({ data: mappingReviewQueue })
    vi.mocked(screenerApi.getSupplyChainNode).mockResolvedValue({ data: { node_id: 'x', companies: [], evidence: [] } } as any)
    vi.mocked(chainApi.deconstructChain).mockResolvedValue({ data: chainDeconstructResponse } as any)
    vi.mocked(chainApi.interpretPolicy).mockResolvedValue({ data: { status: 'disabled' } } as any)
    vi.mocked(chainApi.getNodeCompanies).mockResolvedValue({ data: { companies: [] } } as any)
    vi.mocked(chainApi.getCandidates).mockResolvedValue({
      data: { candidates: [], total_count: 0, elapsed_ms: 1, filter_summary: {}, resonance_summary: {} },
    } as any)
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  // AC①：默认 upstream_downstream 模式专属渲染（graph 图 + 拓扑提示）
  it('默认 upstream 模式：渲染上下游拓扑图（graph），非通用壳', async () => {
    renderSupplyChain()
    await waitFor(() => {
      expect(chainApi.deconstructChain).toHaveBeenCalledWith(
        expect.objectContaining({ method: 'upstream_downstream' }),
      )
    })
    // graph-chart 在 upstream 模式渲染（series[0].type === 'graph'）
    const graphCharts = await screen.findAllByTestId('graph-chart')
    expect(graphCharts.length).toBeGreaterThan(0)
    // upstream 模式展示拓扑提示文案（专属，非 value/competition 注释卡）
    await waitFor(() => {
      expect(screen.getByText(/上下游图展示节点拓扑/)).toBeInTheDocument()
    })
  })

  // AC①：勾选 value_chain overlay → 调 deconstructChain(overlays:[value_chain]) + 渲染 bar 图 + 价值链注释卡
  it('value_chain overlay：method 保持 upstream + 渲染毛利率 bar 图 + 价值链注释卡', async () => {
    renderSupplyChain()
    await screen.findByTestId('graph-chart')

    fireEvent.click(screen.getByRole('checkbox', { name: /价值链/ }))

    await waitFor(() => {
      expect(chainApi.deconstructChain).toHaveBeenCalledWith(
        expect.objectContaining({ method: 'upstream_downstream', overlays: ['value_chain'] }),
      )
    })
    // 价值链注释卡标题（preview mode-note 对齐）
    await waitFor(() => {
      expect(screen.getByText('最高毛利环节')).toBeInTheDocument()
      expect(screen.getByText('利润兑现')).toBeInTheDocument()
      expect(screen.getByText('低毛利环节')).toBeInTheDocument()
    })
  })

  // AC①：勾选 competition overlay → 渲染 scatter 图 + 竞争格局注释卡
  it('competition overlay：渲染竞争格局注释卡（寡头垄断/国产突破/分散竞争）', async () => {
    renderSupplyChain()
    await screen.findByTestId('graph-chart')

    fireEvent.click(screen.getByRole('checkbox', { name: /竞争格局/ }))

    await waitFor(() => {
      expect(chainApi.deconstructChain).toHaveBeenCalledWith(
        expect.objectContaining({ method: 'upstream_downstream', overlays: ['competition'] }),
      )
    })
    await waitFor(() => {
      expect(screen.getByText('寡头垄断')).toBeInTheDocument()
      expect(screen.getByText('国产突破')).toBeInTheDocument()
      expect(screen.getByText('分散竞争')).toBeInTheDocument()
    })
  })

  // AC②：overlay 叠加后图表类型共存（主视图 graph 常显, value=bar, competition=scatter）
  it('overlay 图表类型共存于单树主视图（graph + bar + scatter）', async () => {
    renderSupplyChain()
    await screen.findByTestId('graph-chart')

    // 主视图 → graph
    let charts = screen.getAllByTestId('graph-chart')
    expect(charts.some(c => c.getAttribute('data-chart-type') === 'graph')).toBe(true)

    // value_chain overlay → bar（主 series）
    fireEvent.click(screen.getByRole('checkbox', { name: /价值链/ }))
    await waitFor(() => {
      charts = screen.getAllByTestId('graph-chart')
      expect(charts.some(c => c.getAttribute('data-chart-type') === 'bar')).toBe(true)
    })

    // competition overlay → scatter（与 bar 共存, 主 graph 仍在）
    fireEvent.click(screen.getByRole('checkbox', { name: /竞争格局/ }))
    await waitFor(() => {
      charts = screen.getAllByTestId('graph-chart')
      expect(charts.some(c => c.getAttribute('data-chart-type') === 'scatter')).toBe(true)
    })
    charts = screen.getAllByTestId('graph-chart')
    expect(charts.some(c => c.getAttribute('data-chart-type') === 'graph')).toBe(true)
    expect(charts.some(c => c.getAttribute('data-chart-type') === 'bar')).toBe(true)
  })

  // AC③：缺数据 EmptyState——deconstructChain 返回空树时展示占位
  it('deconstructChain 返回空树时展示缺数据占位', async () => {
    vi.mocked(chainApi.deconstructChain).mockResolvedValue({
      data: { theme: { id: 't', name: '空主题' }, view: 'upstream_downstream', tree: null },
    } as any)
    renderSupplyChain()
    await waitFor(() => {
      expect(screen.getByText(/暂无该主题的拆解节点/)).toBeInTheDocument()
    })
  })
})
