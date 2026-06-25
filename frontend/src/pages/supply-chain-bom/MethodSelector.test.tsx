import { fireEvent, render, screen } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import MethodSelector from './MethodSelector'

describe('MethodSelector', () => {
  it('renders three view tabs: upstream_downstream, value_chain, competition', () => {
    const handleChange = vi.fn()
    render(
      <ConfigProvider locale={zhCN}>
        <MethodSelector value="upstream_downstream" onChange={handleChange} />
      </ConfigProvider>,
    )

    expect(screen.getByRole('radio', { name: /上下游/ })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /价值链/ })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /竞争格局/ })).toBeInTheDocument()
  })

  it('shows current selection highlighted', () => {
    const handleChange = vi.fn()
    render(
      <ConfigProvider locale={zhCN}>
        <MethodSelector value="value_chain" onChange={handleChange} />
      </ConfigProvider>,
    )

    const valueChainRadio = screen.getByRole('radio', { name: /价值链/ })
    expect(valueChainRadio).toBeChecked()
  })

  it('calls onChange when user clicks a different tab', () => {
    const handleChange = vi.fn()
    render(
      <ConfigProvider locale={zhCN}>
        <MethodSelector value="upstream_downstream" onChange={handleChange} />
      </ConfigProvider>,
    )

    fireEvent.click(screen.getByRole('radio', { name: /竞争格局/ }))

    expect(handleChange).toHaveBeenCalledWith('competition')
  })

  it('disables all tabs when disabled prop is true', () => {
    const handleChange = vi.fn()
    render(
      <ConfigProvider locale={zhCN}>
        <MethodSelector value="upstream_downstream" onChange={handleChange} disabled />
      </ConfigProvider>,
    )

    expect(screen.getByRole('radio', { name: /上下游/ })).toBeDisabled()
    expect(screen.getByRole('radio', { name: /价值链/ })).toBeDisabled()
    expect(screen.getByRole('radio', { name: /竞争格局/ })).toBeDisabled()
  })

  it('disables all tabs when loading prop is true', () => {
    const handleChange = vi.fn()
    render(
      <ConfigProvider locale={zhCN}>
        <MethodSelector value="upstream_downstream" onChange={handleChange} loading />
      </ConfigProvider>,
    )

    expect(screen.getByRole('radio', { name: /上下游/ })).toBeDisabled()
    expect(screen.getByRole('radio', { name: /价值链/ })).toBeDisabled()
    expect(screen.getByRole('radio', { name: /竞争格局/ })).toBeDisabled()
  })

  it('shows description for current selected method', () => {
    const handleChange = vi.fn()
    render(
      <ConfigProvider locale={zhCN}>
        <MethodSelector value="competition" onChange={handleChange} />
      </ConfigProvider>,
    )

    expect(screen.getByText('竞争格局')).toBeInTheDocument()
    expect(screen.getByText('市场竞争态势与集中度')).toBeInTheDocument()
  })
})