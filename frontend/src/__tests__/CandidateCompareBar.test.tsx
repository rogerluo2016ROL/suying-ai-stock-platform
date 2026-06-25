import { fireEvent, render, screen } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import CandidateCompareBar from '../pages/supply-chain-bom/CandidateCompareBar'
import type { CandidateCompany } from '../pages/supply-chain-bom/types'

const candidates: CandidateCompany[] = [
  {
    code: '301526',
    name: '国际复材',
    node_name: '材料',
    mapping_confidence: 0.82,
    mapping_adjusted_score: 84,
    mapping_source: 'introduction',
    evidence_gaps: ['客户名单待补'],
    products: ['电子级玻璃布'],
    report_titles: ['电子材料国产替代'],
  },
]

it('opens a detailed comparison drawer with evidence quality fields', () => {
  render(
    <ConfigProvider locale={zhCN}>
      <CandidateCompareBar candidates={candidates} />
    </ConfigProvider>,
  )

  fireEvent.click(screen.getByRole('button', { name: /对比详情/ }))

  expect(screen.getByRole('dialog')).toBeInTheDocument()
  expect(screen.getAllByText('证据评分').length).toBeGreaterThan(0)
  expect(screen.getByText('电子材料国产替代')).toBeInTheDocument()
})
