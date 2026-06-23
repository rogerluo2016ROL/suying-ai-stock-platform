import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import SupplyChainBom from '../pages/SupplyChainBom'
import { screenerApi } from '../api/client'

vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="bom-chart" />,
}))

vi.mock('../api/client', () => ({
  screenerApi: {
    getSupplyChainThemes: vi.fn(),
    getSupplyChainBom: vi.fn(),
    getSupplyChainWorkbench: vi.fn(),
    getSupplyChainNode: vi.fn(),
    getSupplyChainCompany: vi.fn(),
    extractSupplyChainFacts: vi.fn(),
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

describe('SupplyChainBom', () => {
  beforeEach(() => {
    vi.mocked(screenerApi.getSupplyChainThemes).mockResolvedValue({ data: { themes } } as any)
    vi.mocked(screenerApi.getSupplyChainBom).mockResolvedValue({ data: { nodes, edges: [] } } as any)
    vi.mocked((screenerApi as any).getSupplyChainWorkbench).mockResolvedValue({ data: workbench })
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
  })

  it('renders policy themes and drills into a BOM node', async () => {
    render(
      <ConfigProvider locale={zhCN}>
        <SupplyChainBom />
      </ConfigProvider>,
    )

    expect((await screen.findAllByText('未来产业主攻方向')).length).toBeGreaterThan(0)
    expect(screen.getByTestId('bom-chart')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /具身智能/ }))

    await waitFor(() => {
      expect(screen.getAllByText('减速器').length).toBeGreaterThan(0)
    })
  })

  it('shows candidate companies with selection reason, commercialization stage, and resonance', async () => {
    render(
      <ConfigProvider locale={zhCN}>
        <SupplyChainBom />
      </ConfigProvider>,
    )

    expect(await screen.findByText('候选公司池')).toBeInTheDocument()
    expect(screen.getByText('中际旭创')).toBeInTheDocument()
    expect(screen.getByText('高速光模块')).toBeInTheDocument()
    expect(screen.getByText('规模推广')).toBeInTheDocument()
    expect(screen.getByText('业绩兑现')).toBeInTheDocument()
    expect(screen.getByText('128.56')).toBeInTheDocument()
    expect(screen.getByText('+3.21%')).toBeInTheDocument()
    expect(screen.getAllByText('2026-06-22').length).toBeGreaterThan(0)
    expect(screen.getAllByText('政策、商业化、业绩三维共振').length).toBeGreaterThan(0)
    expect(screen.getByText(/中际旭创入选AI算力-硬件环节/)).toBeInTheDocument()
    expect(screen.getByText('政策力度')).toBeInTheDocument()
    expect(screen.getByText('商业化阶段')).toBeInTheDocument()
  })

  it('shows data freshness, report ingestion status, and policy interpretation', async () => {
    render(
      <ConfigProvider locale={zhCN}>
        <SupplyChainBom />
      </ConfigProvider>,
    )

    expect(await screen.findByText('行情更新至 2026-06-22')).toBeInTheDocument()
    expect(screen.getByText('研报更新至 2026-06-09')).toBeInTheDocument()
    expect(screen.getByText('研报库已接入')).toBeInTheDocument()
    expect(screen.getByText('LLM自动抽取未开启')).toBeInTheDocument()
    expect(screen.getByText('研报批量入口已就绪')).toBeInTheDocument()
    expect(screen.getByText('115106篇研报')).toBeInTheDocument()
    expect(screen.getByText('Tushare研报库已接入，最新研报日期 2026-06-09，但LLM批量抽取和图谱写入调度尚未开启。')).toBeInTheDocument()
    expect(screen.getByText('未来产业主攻方向强调前瞻布局，重点寻找可能形成新赛道和新动能的硬科技产业。')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /新质生产力/ }))
    expect(screen.getByText('新质生产力不是普通主题概念，而是以科技创新推动产业深度转型升级的生产力跃迁。')).toBeInTheDocument()
  })

  it('shows upstream influence observation candidates outside the downstream sector board', async () => {
    render(
      <ConfigProvider locale={zhCN}>
        <SupplyChainBom />
      </ConfigProvider>,
    )

    expect(await screen.findByText('上游影响观察池')).toBeInTheDocument()
    expect(screen.getByText('世名科技')).toBeInTheDocument()
    expect(screen.getByText('染料涂料')).toBeInTheDocument()
    expect(screen.getByText('功能色浆/纳米材料')).toBeInTheDocument()
    expect(screen.getByText('世名科技 → 功能色浆/纳米材料 → 显示材料')).toBeInTheDocument()
    expect(screen.getByText('产品是否进入战略产业客户供应链')).toBeInTheDocument()
    expect(screen.getByText('23.05')).toBeInTheDocument()
    expect(screen.getByText('+19.99%')).toBeInTheDocument()
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

    render(
      <ConfigProvider locale={zhCN}>
        <SupplyChainBom />
      </ConfigProvider>,
    )

    fireEvent.click(await screen.findByRole('button', { name: /具身智能/ }))

    await waitFor(() => {
      expect((screenerApi as any).getSupplyChainWorkbench).toHaveBeenCalledWith({
        topN: 30,
        nodeId: 'embodied_ai_core',
        themeId: 'future_industry_core',
      })
    })
    expect(await screen.findByText('绿的谐波')).toBeInTheDocument()
    expect(screen.getByText('谐波减速器')).toBeInTheDocument()
    expect(screen.queryByText('中际旭创')).not.toBeInTheDocument()
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

    render(
      <ConfigProvider locale={zhCN}>
        <SupplyChainBom />
      </ConfigProvider>,
    )

    fireEvent.click(await screen.findByRole('button', { name: /量子科技/ }))

    expect(await screen.findByText('该节点缺少公司映射证据')).toBeInTheDocument()
    expect(screen.queryByText('中际旭创')).not.toBeInTheDocument()
  })

  it('opens a company research card with products, financials, score, moat and resonance', async () => {
    vi.mocked(screenerApi.getSupplyChainCompany).mockResolvedValue({ data: greenHarmonic } as any)

    render(
      <ConfigProvider locale={zhCN}>
        <SupplyChainBom />
      </ConfigProvider>,
    )

    fireEvent.click(await screen.findByText('中际旭创'))

    expect(await screen.findByText('财务指标')).toBeInTheDocument()
    expect(screen.getByText('评分拆解')).toBeInTheDocument()
    expect(screen.getByText('护城河证据')).toBeInTheDocument()
    expect(screen.getByText('谐波减速器')).toBeInTheDocument()
    expect(screen.getAllByText('政策、商业化、业绩三维共振').length).toBeGreaterThan(0)
    expect(screen.getByText('谐波减速器专利与客户认证')).toBeInTheDocument()
  })

  it('submits announcement text to the LLM extraction endpoint', async () => {
    render(
      <ConfigProvider locale={zhCN}>
        <SupplyChainBom />
      </ConfigProvider>,
    )

    const input = await screen.findByPlaceholderText('粘贴政策、公告、研报文本')
    fireEvent.change(input, { target: { value: '公司公告：具身智能关节模组已小批量交付' } })
    fireEvent.click(screen.getByRole('button', { name: /抽取图谱/ }))

    await waitFor(() => {
      expect(screenerApi.extractSupplyChainFacts).toHaveBeenCalledWith(
        '公司公告：具身智能关节模组已小批量交付',
        { source_type: 'manual_paste' },
        false,
      )
      expect(screen.getByText('映射 1')).toBeInTheDocument()
      expect(screen.getByText('证据 1')).toBeInTheDocument()
    })
  })

  it('can request persisting extracted records for review', async () => {
    render(
      <ConfigProvider locale={zhCN}>
        <SupplyChainBom />
      </ConfigProvider>,
    )

    fireEvent.change(await screen.findByPlaceholderText('粘贴政策、公告、研报文本'), {
      target: { value: '公司公告：具身智能关节模组已小批量交付' },
    })
    fireEvent.click(screen.getByLabelText('写入待审核图谱'))
    fireEvent.click(screen.getByRole('button', { name: /抽取图谱/ }))

    await waitFor(() => {
      expect(screenerApi.extractSupplyChainFacts).toHaveBeenCalledWith(
        '公司公告：具身智能关节模组已小批量交付',
        { source_type: 'manual_paste' },
        true,
      )
    })
  })
})
