import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Result, Button } from 'antd'

interface ErrorBoundaryProps {
  children: ReactNode
  /** Custom fallback; defaults to a full-page 500 result with a reload button. */
  fallback?: (error: Error, reset: () => void) => ReactNode
  /** Called for every caught error (logging). */
  onError?: (error: Error, info: ErrorInfo) => void
}

interface ErrorBoundaryState {
  error: Error | null
}

/**
 * App-level error boundary. React 18 otherwise unmounts the whole tree on any
 * child throw → full white screen. This boundary renders a recoverable fallback.
 *
 * Use a single instance wrapping the whole App (see main.tsx), plus finer-grained
 * instances around volatile areas like ECharts containers.
 */
export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // eslint-disable-next-line no-console
    console.error('[ErrorBoundary] caught render error', error, info)
    this.props.onError?.(error, info)
  }

  reset = (): void => {
    this.setState({ error: null })
  }

  render(): ReactNode {
    if (this.state.error) {
      if (this.props.fallback) {
        return this.props.fallback(this.state.error, this.reset)
      }
      return (
        <Result
          status="500"
          title="页面出错了"
          subTitle="渲染过程中发生异常，您可以尝试刷新页面恢复。"
          extra={
            <Button type="primary" onClick={() => window.location.reload()}>
              刷新页面
            </Button>
          }
        />
      )
    }
    return this.props.children
  }
}
