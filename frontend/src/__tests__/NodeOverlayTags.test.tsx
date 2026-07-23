import { render, screen } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import NodeOverlayTags from '../pages/supply-chain-bom/NodeOverlayTags'

const node = {
  transmission_layer_name: '核心产品',
  value_chain: { margin: 32, pricing_power: 4, value_added: 15, note: '毛利率32%, 定价权强, 附加值15%' },
  competition: { concentration: 80, leader_share: 60, barrier: 5, threat: 2, note: '高集中度, 龙头份额60%, 高壁垒, 低威胁' },
}

function renderTags(props: Partial<Parameters<typeof NodeOverlayTags>[0]> = {}) {
  return render(
    <ConfigProvider locale={zhCN}>
      <NodeOverlayTags node={node} overlays={[]} {...props} />
    </ConfigProvider>,
  )
}

describe('NodeOverlayTags', () => {
  it('always shows transmission_layer_name tag when present', () => {
    renderTags()

    expect(screen.getByText('核心产品')).toBeInTheDocument()
  })

  it('hides overlay labels when overlays are not enabled', () => {
    renderTags()

    expect(screen.queryByText(/毛利/)).not.toBeInTheDocument()
    expect(screen.queryByText(/集中度/)).not.toBeInTheDocument()
  })

  it('shows value_chain labels when value_chain overlay is enabled', () => {
    renderTags({ overlays: ['value_chain'] })

    expect(screen.getByText('毛利 32% · 议价权 4 · 增值 15%')).toBeInTheDocument()
    expect(screen.queryByText(/集中度/)).not.toBeInTheDocument()
  })

  it('shows competition labels when competition overlay is enabled', () => {
    renderTags({ overlays: ['competition'] })

    expect(screen.getByText('集中度 80% · 龙头 60% · 壁垒 5 · 威胁 2')).toBeInTheDocument()
    expect(screen.queryByText(/毛利/)).not.toBeInTheDocument()
  })

  it('shows both overlay label groups when both overlays are enabled', () => {
    renderTags({ overlays: ['value_chain', 'competition'] })

    expect(screen.getByText(/毛利 32%/)).toBeInTheDocument()
    expect(screen.getByText(/集中度 80%/)).toBeInTheDocument()
  })

  it('renders nothing when node has no labels at all', () => {
    const { container } = renderTags({ node: {} })

    expect(container).toBeEmptyDOMElement()
  })

  it('skips null overlay metrics but keeps available ones', () => {
    renderTags({
      overlays: ['value_chain'],
      node: { value_chain: { margin: null, pricing_power: 2, value_added: null, note: '定价权中' } },
    })

    expect(screen.getByText('议价权 2')).toBeInTheDocument()
  })

  it('renders only transmission tag when overlay data missing on node', () => {
    renderTags({ overlays: ['value_chain', 'competition'], node: { transmission_layer_name: '基础设施' } })

    expect(screen.getByText('基础设施')).toBeInTheDocument()
    expect(screen.queryByText(/毛利/)).not.toBeInTheDocument()
    expect(screen.queryByText(/集中度/)).not.toBeInTheDocument()
  })
})
