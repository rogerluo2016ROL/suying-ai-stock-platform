import { render, screen } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import SupplyChainCandidateGrid from '../pages/supply-chain-bom/SupplyChainCandidateGrid'
import type { CandidateCompany } from '../pages/supply-chain-bom/types'

const candidates: CandidateCompany[] = [{
  code: '300308',
  name: '中际旭创',
  industry: '通信设备',
  chain: 'AI算力',
  layer: '硬件',
  score: 72.4,
  mapping_adjusted_score: 72.4,
  mapping_status: 'verified',
  mapping_source: 'main_business',
  mapping_confidence: 0.85,
  evidence_gaps: [],
  financial_indicators: { revenue_growth: 192.1, profit_growth: 571.8, roe: 17.5, gross_margin: 46.1 },
}]

it('renders mapping-adjusted score and mapping status without wrapping core cells', () => {
  render(
    <ConfigProvider locale={zhCN}>
      <SupplyChainCandidateGrid
        candidates={candidates}
        selectedCodes={[]}
        onToggleCompare={() => {}}
        onOpenCompany={() => {}}
      />
    </ConfigProvider>,
  )

  expect(screen.getByText('中际旭创')).toBeInTheDocument()
  expect(screen.getAllByText('72.4').length).toBeGreaterThan(0)
  expect(screen.getByText('已确认')).toBeInTheDocument()
  expect(screen.getByTestId('candidate-grid-wrap')).toHaveStyle({ whiteSpace: 'nowrap' })
})

it('supports selecting candidates for comparison', () => {
  const onToggleCompare = vi.fn()
  render(
    <ConfigProvider locale={zhCN}>
      <SupplyChainCandidateGrid
        candidates={candidates}
        selectedCodes={[]}
        onToggleCompare={onToggleCompare}
        onOpenCompany={() => {}}
      />
    </ConfigProvider>,
  )

  screen.getByRole('checkbox', { name: /对比 中际旭创/ }).click()

  expect(onToggleCompare).toHaveBeenCalledWith(candidates[0])
})
