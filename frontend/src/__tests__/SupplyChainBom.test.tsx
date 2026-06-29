import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { MemoryRouter } from 'react-router-dom'
import SupplyChainBom from '../pages/SupplyChainBom'
import { screenerApi, chainApi } from '../api/client'

vi.mock('echarts-for-react', () => ({
  default: ({ option }: any) => {
    // Distinguish between tree chart and graph chart based on option type
    const isTree = option?.series?.[0]?.type === 'tree'
    return <div data-testid={isTree ? 'tree-chart' : 'graph-chart'} />
  },
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

// P2-08: Mock both screenerApi and chainApi
vi.mock('../api/client', () => ({
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
  keywords: ['量子科技', '具身智能'],
  node_count: 2,
  matrix: { policy_weight: 1.5, high_growth: null, high_profit: null, high_moat: null },
  interpretation: '未来产业主攻方向强调前瞻布局，重点寻找可能形成新赛道和新动能的硬科技产业。',
}, {
  theme_id: 'new_quality_productivity',
  name: '新质生产力',
  policy_weight: 1.3,
  keywords: ['新质生产力', '硬科技'],
  node_count: 0,
  matrix: { policy_weight: 1.3, high_growth: null, high_profit: null, high_moat: null },
  interpretation: '新质生产力不是普通主题概念，而是以科技创新推动产业深度转型升级的生产力跃迁。',
}]

const nodes = [
  {
    node_id: 'quantum_core',
    theme_id: 'future_industry_core',
    chain_id: 'quantum',
    level: 'chain',
    name: '量子科技',
    node_type: 'industry',
    keywords: ['量子计算'],
    policy_theme: '未来产业主攻方向',
    bom_path: ['未来产业主攻方向', '量子科技'],
    companies: [],
  },
  {
    node_id: 'embodied_ai_core',
    theme_id: 'future_industry_core',
    chain_id: 'embodied_ai',
    level: 'chain',
    name: '具身智能',
    node_type: 'industry',
    keywords: ['具身智能', '伺服', '减速器'],
    policy_theme: '未来产业主攻方向',
    bom_path: ['未来产业主攻方向', '具身智能'],
    companies: [],
  },
]

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
        children: [
          {
            node_id: 'quantum_compute',
            name: '量子计算',
            layer: 3,
            children: [],
          },
        ],
      },
      {
        node_id: 'embodied_ai_core',
        name: '具身智能',
        layer: 2,
        children: [],
      },
    ],
  },
}

const workbench = {
  model: {
    name: '大葱产业链解构选股模型 V4',
    score_dimensions: [
      { key: 'policy', name: '政策力度', weight: 15 },
      { key: 'commercialization', name: '商业化阶段', weight: 15 },
    ],
  },
  themes,
  nodes,
  edges: [],
  candidate_count: 1,
  selected_node_thesis: {},
  node_candidate_count: 0,
  node_candidate_companies: [],
  candidates: [{
    code: '300308',
    name: '中际旭创',
    chain: 'AI算力',
    layer: '硬件',
    score: 72.4,
    rating: 'B',
    trade_signal: '观察',
    products: ['高速光模块'],
    materials: ['光芯片'],
    last_trade_date: '2026-06-22',
    last_price: 128.56,
    last_change_pct: 3.21,
    selection_reason: '中际旭创入选AI算力-硬件环节，核心产品/能力为高速光模块，商业化阶段为规模推广。',
    commercialization_stage: '规模推广',
    commercialization_cycle: '业绩兑现',
    resonance: { summary: '政策、商业化、业绩三维共振' },
    dimension_scores: { policy: 12, bom: 14, commercialization: 13, growth: 15, profit: 8, market: 5 },
    financial_indicators: { revenue_growth: 192.1, profit_growth: 571.8, roe: 17.5, gross_margin: 46.1 },
    moat_evidence: [{ evidence_type: 'moat_signal', summary: '行业龙头' }],
  }],
  data_freshness: {
    market: { latest_trade_date: '2026-06-22', row_count: 8563922 },
    research_reports: { latest_pub_date: '2026-06-09', row_count: 115106 },
    broker_recommend: { latest_month: '202606', row_count: 17347 },
  },
  research_ingestion: {
    auto_collection_status: 'local_catalog_available',
    llm_auto_extract_enabled: false,
    manual_extract_available: true,
    batch_extract_endpoint: '/api/v1/screener/supply-chain/research/ingest',
    source_latest_pub_date: '2026-06-09',
    source_row_count: 115106,
    message: 'Tushare研报库已接入，最新研报日期 2026-06-09，但LLM批量抽取和图谱写入调度尚未开启。',
  },
  upstream_influence_count: 1,
  upstream_influence_candidates: [{
    code: '300522',
    name: '世名科技',
    industry: '染料涂料',
    chain: '上游影响',
    layer: '功能色浆/纳米材料',
    score: 60,
    rating: '观察',
    trade_signal: '观察',
    candidate_source: 'upstream_influence',
    pool_status: '观察池',
    policy_theme: '新质生产力',
    upstream_node: '功能色浆/纳米材料',
    impact_role: '上游功能材料',
    downstream_chains: ['显示材料', '新材料', '高端制造'],
    influence_paths: ['世名科技 → 功能色浆/纳米材料 → 显示材料'],
    evidence_gaps: ['产品是否进入战略产业客户供应链', '是否有量产/扩产/客户验证公告'],
    last_trade_date: '2026-06-22',
    last_price: 23.05,
    last_change_pct: 19.99,
    selection_reason: '世名科技不因染料涂料行业被排除，作为上游功能材料进入上游影响观察池。',
  }],
}

const greenHarmonic = {
  code: '688017',
  name: '绿的谐波',
  chain: '机器人',
  layer: '减速器',
  score: 78.5,
  rating: 'A',
  trade_signal: '启动',
  products: ['谐波减速器'],
  materials: ['高精密轴承材料'],
  selection_reason: '绿的谐波卡位具身智能减速器节点，量产爬坡阶段。',
  commercialization_stage: '量产爬坡',
  commercialization_cycle: '量产启动',
  resonance: { summary: '政策、商业化、业绩三维共振' },
  dimension_scores: { policy: 13, bom: 14, commercialization: 13 },
  financial_indicators: { revenue_growth: 28.5, profit_growth: 31.2, roe: 15.2, gross_margin: 44.1 },
  moat_evidence: [{ evidence_type: 'patent', summary: '谐波减速器专利与客户认证' }],
}

const mappingQuality = {
  mapping_count: 15642,
  review_queue_count: 14573,
  status_counts: {
    verified: 1069,
    pending_review: 10547,
    weak_evidence: 4026,
  },
  source_counts: {
    main_business: 4366,
  },
  hotspot_nodes: [{
    node_id: 'advanced_manufacturing_integration',
    node_name: '集成',
    chain_id: 'advanced_manufacturing',
    verified: 24,
    pending_review: 846,
    weak_evidence: 68,
    rejected: 0,
    review_pressure: 914,
  }],
}

const mappingReviewQueue = {
  total: 14573,
  limit: 20,
  offset: 0,
  items: [{
    code: '301526',
    name: '国际复材',
    node_id: 'semiconductor_materials',
    node_name: '材料',
    chain_id: 'semiconductor',
    product_name: '电子级玻璃布',
    confidence: 0.8,
    status: 'pending_review',
    mapping_source: 'introduction',
    evidence: ['电子级玻璃布'],
    evidence_gaps: ['是否有明确客户或供应链认证'],
    review_priority: 92,
  }],
}

const policyInterpretResponse = {
  status: 'ok',
  interpretation_result: {
    summary: '政策强调发展量子科技产业',
    industry_themes: [{ name: '量子科技', weight: 1.5 }],
    bom_nodes: ['量子计算', '量子通信'],
    investment_logic: '量子科技是未来产业主攻方向',
    risk_factors: [{ name: '商业化进度低于预期' }],
  },
  usage: {
    prompt_tokens: 500,
    completion_tokens: 200,
    total_tokens: 700,
    provider: 'deepseek',
    model: 'deepseek-chat',
  },
  persisted: false,
}

function renderSupplyChain(initialRoute = '/supply-chain-bom') {
  return render(
    <ConfigProvider locale={zhCN}>
      <MemoryRouter initialEntries={[initialRoute]}>
        <SupplyChainBom />
      </MemoryRouter>
    </ConfigProvider>,
  )
}

describe('SupplyChainBom', () => {
  beforeEach(() => {
    vi.mocked(screenerApi.getSupplyChainThemes).mockResolvedValue({ data: { themes } } as any)
    vi.mocked(screenerApi.getSupplyChainBom).mockResolvedValue({ data: { nodes, edges: [] } } as any)
    vi.mocked((screenerApi as any).getSupplyChainWorkbench).mockResolvedValue({ data: workbench })
    vi.mocked((screenerApi as any).getSupplyChainMappingQuality).mockResolvedValue({ data: mappingQuality })
    vi.mocked((screenerApi as any).getSupplyChainMappingReviewQueue).mockResolvedValue({ data: mappingReviewQueue })
    vi.mocked((screenerApi as any).reviewSupplyChainMapping).mockResolvedValue({ data: { status: 'ok' } })
    vi.mocked(screenerApi.getSupplyChainNode).mockImplementation((nodeId: string) => {
      const node = nodes.find(n => n.node_id === nodeId)
      return Promise.resolve({ data: { node_id: nodeId, node, companies: [], evidence: [] } }) as any
    })
    vi.mocked(screenerApi.extractSupplyChainFacts).mockResolvedValue({
      data: {
        status: 'ok',
        persisted: false,
        records: { mappings: [{ code: '688001' }], evidence: [{ summary: '小批量交付' }] },
      },
    } as any)

    // P2-08: Mock chainApi
    vi.mocked(chainApi.deconstructChain).mockResolvedValue({ data: chainDeconstructResponse } as any)
    vi.mocked(chainApi.interpretPolicy).mockResolvedValue({ data: policyInterpretResponse } as any)
    vi.mocked(chainApi.getNodeCompanies).mockResolvedValue({ data: { companies: [] } } as any)
    vi.mocked(chainApi.getCandidates).mockResolvedValue({
      data: {
        candidates: [],
        total_count: 0,
        elapsed_ms: 1,
        filter_summary: { all: 0, high_growth: 0, high_profit: 0, high_moat: 0, chokepoint_core: 0 },
        resonance_summary: { 强启动: 0, 启动: 0, 关注: 0, 观察: 0 },
      },
    } as any)
  })

  it('renders policy themes and drills into a BOM node', async () => {
    renderSupplyChain()

    expect(screen.getByRole('tab', { name: /政策梳理/ })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /产业链解构/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: /多维度分析/ })).toBeInTheDocument()
    expect((await screen.findAllByText('未来产业主攻方向')).length).toBeGreaterThan(0)
    expect(screen.getByTestId('tree-chart')).toBeInTheDocument()
    expect(screen.getByTestId('graph-chart')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'apartment具身智能' }))

    await waitFor(() => {
      expect(screenerApi.getSupplyChainWorkbench).toHaveBeenCalledWith({
        topN: 30,
        nodeId: 'embodied_ai_core',
        themeId: 'future_industry_core',
      })
    })
  })

  it('shows candidate companies with selection reason, commercialization stage, and resonance', async () => {
    renderSupplyChain()

    expect(await screen.findByText('候选公司池')).toBeInTheDocument()
    expect(screen.getAllByText('中际旭创').length).toBeGreaterThan(0)
    expect(screen.getAllByText('高速光模块').length).toBeGreaterThan(0)
    expect(screen.getByText('128.56')).toBeInTheDocument()
    expect(screen.getByText('+3.21%')).toBeInTheDocument()
    expect(screen.getAllByText('2026-06-22').length).toBeGreaterThan(0)
    expect(screen.getAllByText('政策、商业化、业绩三维共振').length).toBeGreaterThan(0)
    expect(screen.getByText(/中际旭创入选AI算力-硬件环节/)).toBeInTheDocument()
    expect(screen.getByText('政策力度')).toBeInTheDocument()
    expect(screen.getByText('商业化阶段')).toBeInTheDocument()
  })

  it('shows data freshness, report ingestion status, and policy interpretation', async () => {
    renderSupplyChain()

    expect(await screen.findByText('数据更新')).toBeInTheDocument()
    expect(screen.getAllByText('2026-06-22').length).toBeGreaterThan(0)
    expect(screen.getByText('研报 2026-06-09')).toBeInTheDocument()
    expect(screen.getAllByText('研报库已接入').length).toBeGreaterThan(0)
    expect(screen.getByText('未来产业主攻方向强调前瞻布局，重点寻找可能形成新赛道和新动能的硬科技产业。')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '新质生产力' }))
    expect(screen.getByText('新质生产力不是普通主题概念，而是以科技创新推动产业深度转型升级的生产力跃迁。')).toBeInTheDocument()
  })

  it('shows upstream influence observation candidates outside the downstream sector board', async () => {
    renderSupplyChain()

    expect(await screen.findByText('上游影响观察池')).toBeInTheDocument()
    expect(screen.getAllByText('世名科技').length).toBeGreaterThan(0)
    expect(screen.getAllByText('染料涂料').length).toBeGreaterThan(0)
    expect(screen.getAllByText('功能色浆/纳米材料').length).toBeGreaterThan(0)
    expect(screen.getByText('世名科技 → 功能色浆/纳米材料 → 显示材料')).toBeInTheDocument()
    expect(screen.getByText('产品是否进入战略产业客户供应链')).toBeInTheDocument()
    expect(screen.getByText('23.05')).toBeInTheDocument()
    expect(screen.getByText('+19.99%')).toBeInTheDocument()
  })

  it('shows the mapping review workbench with hotspot and queue rows', async () => {
    renderSupplyChain()

    expect(await screen.findByText('映射复核')).toBeInTheDocument()
    expect(screen.getByText('高端制造/集成')).toBeInTheDocument()
    expect(screen.getAllByText('国际复材').length).toBeGreaterThan(0)
    expect(screen.getAllByText('电子级玻璃布').length).toBeGreaterThan(0)
  })

  it('renders the three-column research workbench on the first screen', async () => {
    renderSupplyChain()

    const workbenchRegion = await screen.findByLabelText('产业链拆解工作台')
    expect(within(workbenchRegion).getByText('节点下钻、候选横评、证据复核集中处理')).toBeInTheDocument()
    expect(within(workbenchRegion).getByText('产业链导航')).toBeInTheDocument()
    expect(within(workbenchRegion).getByText('候选对比')).toBeInTheDocument()
    expect(within(workbenchRegion).getByRole('tab', { name: '证据链' })).toBeInTheDocument()
  })

  it('reloads the company pool for the selected BOM node', async () => {
    vi.mocked((screenerApi as any).getSupplyChainWorkbench).mockImplementation((params?: any) => {
      if (params?.nodeId === 'embodied_ai_core') {
        return Promise.resolve({
          data: Object.assign({}, workbench, {
            selected_node_id: 'embodied_ai_core',
            selected_node_thesis: {
              node_id: 'embodied_ai_core',
              name: '具身智能',
              thesis: '具身智能节点需要验证减速器、伺服、控制器等核心部件。',
              mapping_status: 'mapped',
              mapping_message: '已映射 1 家候选上市公司',
              trigger_conditions: ['产品进入量产或规模推广'],
              risk_factors: ['商业化进度低于预期'],
            },
            node_candidate_count: 1,
            node_candidate_companies: [greenHarmonic],
          }),
        })
      }
      return Promise.resolve({ data: workbench })
    })

    renderSupplyChain()

    fireEvent.click(await screen.findByRole('button', { name: 'apartment具身智能' }))

    await waitFor(() => {
      expect((screenerApi as any).getSupplyChainWorkbench).toHaveBeenCalledWith({
        topN: 30,
        nodeId: 'embodied_ai_core',
        themeId: 'future_industry_core',
      })
    })
    await waitFor(() => {
      expect(screen.getAllByText('绿的谐波').length).toBeGreaterThan(0)
    })
    expect(screen.getAllByText('谐波减速器').length).toBeGreaterThan(0)
  })

  it('shows an explicit missing-mapping state instead of global candidates', async () => {
    vi.mocked((screenerApi as any).getSupplyChainWorkbench).mockImplementation((params?: any) => {
      if (params?.nodeId === 'quantum_core') {
        return Promise.resolve({
          data: Object.assign({}, workbench, {
            selected_node_id: 'quantum_core',
            selected_node_thesis: {
              node_id: 'quantum_core',
              name: '量子科技',
              thesis: '量子科技节点需要补充上市公司产品映射证据。',
              mapping_status: 'missing_company_mapping',
              mapping_message: '该节点缺少公司映射证据',
              trigger_conditions: ['政策持续加码'],
              risk_factors: ['商业化进度低于预期'],
            },
            node_candidate_count: 0,
            node_candidate_companies: [],
          }),
        })
      }
      return Promise.resolve({ data: workbench })
    })

    renderSupplyChain()

    fireEvent.click(await screen.findByRole('button', { name: 'apartment量子科技' }))

    expect(await screen.findByText('该节点缺少公司映射证据')).toBeInTheDocument()
    expect(screen.queryByText('中际旭创')).not.toBeInTheDocument()
  })

  it('opens a company research card with products, financials, score, moat and resonance', async () => {
    vi.mocked(screenerApi.getSupplyChainCompany).mockResolvedValue({ data: greenHarmonic } as any)

    renderSupplyChain()

    fireEvent.click(await screen.findByRole('button', { name: 'eye中际旭创' }))

    expect(await screen.findByText('财务指标')).toBeInTheDocument()
    expect(screen.getByText('评分拆解')).toBeInTheDocument()
    expect(screen.getByText('护城河证据')).toBeInTheDocument()
    expect(screen.getAllByText('谐波减速器').length).toBeGreaterThan(0)
    expect(screen.getAllByText('政策、商业化、业绩三维共振').length).toBeGreaterThan(0)
    expect(screen.getByText('谐波减速器专利与客户认证')).toBeInTheDocument()
  })

  // P2-08: Policy interpretation tests (replaces LLM extraction)
  it('submits policy text to the interpretation endpoint', async () => {
    renderSupplyChain()

    const input = await screen.findByPlaceholderText('粘贴政策文件、公告、新闻稿文本，LLM将自动解读并提取产业主题与投资逻辑...')
    fireEvent.change(input, { target: { value: '政策文件：重点发展量子科技产业' } })
    fireEvent.click(screen.getByRole('button', { name: /解读政策/ }))

    await waitFor(() => {
      expect(chainApi.interpretPolicy).toHaveBeenCalledWith(
        '政策文件：重点发展量子科技产业',
        { source_type: 'manual_paste' },
        false,
      )
    })

    // Check that result status is displayed
    await waitFor(() => {
      expect(screen.getByText('解读成功')).toBeInTheDocument()
    })
  })

  it('can request persisting interpreted records for review', async () => {
    renderSupplyChain()

    const input = await screen.findByPlaceholderText('粘贴政策文件、公告、新闻稿文本，LLM将自动解读并提取产业主题与投资逻辑...')
    fireEvent.change(input, { target: { value: '政策文件：重点发展量子科技产业' } })

    // Click checkbox before submitting
    const checkbox = screen.getByLabelText('写入待审核图谱')
    fireEvent.click(checkbox)

    // Now submit
    fireEvent.click(screen.getByRole('button', { name: /解读政策/ }))

    await waitFor(() => {
      expect(chainApi.interpretPolicy).toHaveBeenCalledWith(
        '政策文件：重点发展量子科技产业',
        { source_type: 'manual_paste' },
        true,
      )
    })
  })

  it('shows interpretation result with summary, themes and investment logic', async () => {
    renderSupplyChain()

    const input = await screen.findByPlaceholderText('粘贴政策文件、公告、新闻稿文本，LLM将自动解读并提取产业主题与投资逻辑...')
    fireEvent.change(input, { target: { value: '政策文件：重点发展量子科技产业' } })
    fireEvent.click(screen.getByRole('button', { name: /解读政策/ }))

    await waitFor(() => {
      // Check that interpretPolicy was called
      expect(chainApi.interpretPolicy).toHaveBeenCalled()
    })

    // Check interpretation result is displayed
    await waitFor(() => {
      expect(screen.getByText('政策强调发展量子科技产业')).toBeInTheDocument()
    })
    expect(screen.getAllByText('量子科技').length).toBeGreaterThan(0)
    expect(screen.getAllByText('量子计算').length).toBeGreaterThan(0)
    expect(screen.getByText('量子通信')).toBeInTheDocument()
  })

  // P2-08: Method selector tests
  it('shows three view tabs and triggers chain deconstruct on method change', async () => {
    renderSupplyChain()

    // Wait for initial load and chain deconstruct call
    await waitFor(() => {
      expect(chainApi.deconstructChain).toHaveBeenCalledWith({
        theme_id: 'future_industry_core',
        method: 'upstream_downstream',
      })
    })

    // Click on value_chain tab
    fireEvent.click(screen.getByRole('radio', { name: /价值链/ }))

    await waitFor(() => {
      expect(chainApi.deconstructChain).toHaveBeenCalledWith({
        theme_id: 'future_industry_core',
        method: 'value_chain',
      })
    })
  })
})
