import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ConfigProvider, App as AntdApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import SupplyChainCandidateRankingPanel from '../pages/supply-chain-bom/SupplyChainCandidateRankingPanel'
import { screenerApi } from '../api/client'

vi.mock('../api/client', () => ({
  screenerApi: {
    getSupplyChainCandidateRanking: vi.fn(),
  },
}))

describe('SupplyChainCandidateRankingPanel', () => {
  beforeEach(() => {
    vi.mocked(screenerApi.getSupplyChainCandidateRanking).mockReset()
    vi.mocked(screenerApi.getSupplyChainCandidateRanking).mockResolvedValue({
      data: {
        version: 'supply-chain-candidate-ranking-v1',
        source_status: 'ready',
        filters: { top_n: 100, chain_id: null, signal: null },
        summary: {
          mapping_rows: 2255,
          company_chain_rows: 1219,
          chain_count: 18,
          signal_distribution: { 重点候选: 1, 观察: 92, 暂缓: 1126 },
          bigtech_capex_context: {
            company_count: 5,
            record_count: 13,
            companies: ['Alphabet', 'Amazon', 'Meta', 'Microsoft', 'Oracle'],
          },
        },
        items: [
          {
            rank: 1,
            chain_id: 'ai_compute',
            code: '688498',
            name: '源杰科技',
            industry: '通信设备',
            rank_score: 80.97,
            signal: '重点候选',
            tag_count: 3,
            best_mapping_id: 'auto_688498_ai_compute_hardware',
            best_tag_name: 'AI算力硬件',
            node_id: 'ai_compute_l5_optical_chip',
            mapping_status: 'verified',
            three_high_total: 84,
            growth_score: 82,
            profit_score: 77,
            moat_score: 88,
            stage_score: 70,
            evidence_score: 92,
            expectation_gap_score: 76,
            research_stage: '工程验证',
            commercialization_stage: '批量供货',
            commercialization_indicator: 'C3：海外云厂商CAPEX和数据中心扩张已形成强验证',
            expectation_gap_indicator: 'CAPEX/AI基础设施证据强于普通概念预期',
            trigger_signal_indicator: '海外大厂继续扩张AI数据中心、服务器、网络和云容量',
            bigtech_capex_tailwind: {
              score: 93.33,
              matched_layers: ['demand', 'infrastructure'],
              company_count: 5,
              record_count: 13,
              companies: ['Alphabet', 'Amazon', 'Meta', 'Microsoft', 'Oracle'],
            },
            l8_match_rate: 0.83,
            fresh_rate: 1,
            freshness_status: 'fresh',
            fact_count: 18,
            latest_price: 164.2,
            latest_trade_date: '2026-07-03',
            change_1d_pct: 3.21,
            change_20d_pct: 18.4,
          },
        ],
        by_chain: {
          ai_compute: [],
        },
        limitations: [],
      },
    } as any)
  })

  it('renders real candidate ranking rows and opens the selected company evidence context', async () => {
    const onOpenCompany = vi.fn()
    render(
      <ConfigProvider locale={zhCN}>
        <AntdApp>
          <SupplyChainCandidateRankingPanel onOpenCompany={onOpenCompany} />
        </AntdApp>
      </ConfigProvider>,
    )

    expect(await screen.findByText('候选总榜')).toBeInTheDocument()
    expect(screen.getByText('源杰科技')).toBeInTheDocument()
    expect(screen.getByText('AI算力硬件')).toBeInTheDocument()
    expect(screen.getAllByText('重点候选').length).toBeGreaterThan(0)
    expect(screen.getByText('海外大厂 CAPEX 证据')).toBeInTheDocument()
    expect(screen.getAllByText('5 家大厂').length).toBeGreaterThan(0)
    expect(screen.getAllByText('13 条 SEC 证据').length).toBeGreaterThan(0)
    expect(screen.getByText('大厂顺风 93.3')).toBeInTheDocument()
    expect(screen.getByText('CAPEX/AI基础设施证据强于普通概念预期')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /查看证据/ }))

    await waitFor(() => {
      expect(onOpenCompany).toHaveBeenCalledWith(expect.objectContaining({
        code: '688498',
        name: '源杰科技',
        mapping_id: 'auto_688498_ai_compute_hardware',
        node_id: 'ai_compute_l5_optical_chip',
        score: 80.97,
      }))
    })
  })
})
