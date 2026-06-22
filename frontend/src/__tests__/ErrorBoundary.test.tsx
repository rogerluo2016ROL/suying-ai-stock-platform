import { render, screen } from '@testing-library/react'
import { Button } from 'antd'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import ErrorBoundary from '../components/ErrorBoundary'

function ThrowOnRender({ message }: { message: string }): JSX.Element {
  throw new Error(message)
}

describe('P1-02: ErrorBoundary 捕获渲染错误兜底', () => {
  // Silence React's expected error logging for these intentional throws.
  const spy = vi.spyOn(console, 'error').mockImplementation(() => {})

  afterAll(() => spy.mockRestore())

  it('子组件抛错 → 渲染 500 fallback 含刷新按钮，不白屏', () => {
    render(
      <ConfigProvider locale={zhCN}>
        <ErrorBoundary>
          <ThrowOnRender message="boom" />
        </ErrorBoundary>
      </ConfigProvider>,
    )

    expect(screen.getByText('页面出错了')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '刷新页面' })).toBeInTheDocument()
  })

  it('支持自定义 fallback', () => {
    render(
      <ErrorBoundary fallback={(err) => <div>自定义错误：{err.message}</div>}>
        <ThrowOnRender message="custom-boom" />
      </ErrorBoundary>,
    )

    expect(screen.getByText('自定义错误：custom-boom')).toBeInTheDocument()
  })

  it('正常子树不受影响', () => {
    render(
      <ErrorBoundary>
        <Button>正常按钮</Button>
      </ErrorBoundary>,
    )

    expect(screen.getByRole('button', { name: '正常按钮' })).toBeInTheDocument()
  })
})
