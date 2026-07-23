import { fireEvent, render, screen } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import MethodSelector from '../pages/supply-chain-bom/MethodSelector'

function renderSelector(overlays: Array<'value_chain' | 'competition'> = [], extra: { loading?: boolean; disabled?: boolean } = {}) {
  const handleChange = vi.fn()
  render(
    <ConfigProvider locale={zhCN}>
      <MethodSelector overlays={overlays} onOverlaysChange={handleChange} {...extra} />
    </ConfigProvider>,
  )
  return handleChange
}

describe('MethodSelector (单树视图 + overlay 开关)', () => {
  it('renders fixed upstream_downstream main view tag and two overlay toggles', () => {
    renderSelector()

    expect(screen.getByText('上下游拆解')).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /价值链/ })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /竞争格局/ })).toBeInTheDocument()
  })

  it('checks overlay toggles that are enabled', () => {
    renderSelector(['value_chain'])

    expect(screen.getByRole('checkbox', { name: /价值链/ })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: /竞争格局/ })).not.toBeChecked()
  })

  it('supports enabling both overlays at the same time', () => {
    renderSelector(['value_chain', 'competition'])

    expect(screen.getByRole('checkbox', { name: /价值链/ })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: /竞争格局/ })).toBeChecked()
  })

  it('calls onOverlaysChange with overlay added when toggled on', () => {
    const handleChange = renderSelector([])

    fireEvent.click(screen.getByRole('checkbox', { name: /竞争格局/ }))

    expect(handleChange).toHaveBeenCalledWith(['competition'])
  })

  it('appends to existing overlays when toggling a second overlay on', () => {
    const handleChange = renderSelector(['value_chain'])

    fireEvent.click(screen.getByRole('checkbox', { name: /竞争格局/ }))

    expect(handleChange).toHaveBeenCalledWith(['value_chain', 'competition'])
  })

  it('calls onOverlaysChange with overlay removed when toggled off', () => {
    const handleChange = renderSelector(['value_chain', 'competition'])

    fireEvent.click(screen.getByRole('checkbox', { name: /价值链/ }))

    expect(handleChange).toHaveBeenCalledWith(['competition'])
  })

  it('disables overlay toggles when disabled prop is true', () => {
    renderSelector([], { disabled: true })

    expect(screen.getByRole('checkbox', { name: /价值链/ })).toBeDisabled()
    expect(screen.getByRole('checkbox', { name: /竞争格局/ })).toBeDisabled()
  })

  it('disables overlay toggles when loading prop is true', () => {
    renderSelector([], { loading: true })

    expect(screen.getByRole('checkbox', { name: /价值链/ })).toBeDisabled()
    expect(screen.getByRole('checkbox', { name: /竞争格局/ })).toBeDisabled()
  })

  it('shows description tags for enabled overlays', () => {
    renderSelector(['competition'])

    expect(screen.getByText('叠加集中度/龙头份额/壁垒/威胁标签')).toBeInTheDocument()
    expect(screen.queryByText('叠加毛利率/议价权/价值增值标签')).not.toBeInTheDocument()
  })

  it('shows single-tree hint when no overlay is enabled', () => {
    renderSelector()

    expect(screen.getByText(/单树视图/)).toBeInTheDocument()
  })
})
