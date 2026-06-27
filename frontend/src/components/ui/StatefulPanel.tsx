/* ============================================================
   速赢AI — 状态面板组件

   来源：docs/design/new front/IMPLEMENTATION_PLAN.md 阶段1.4
   用途：统一加载态、空态、错误态处理，支持完整可访问性属性

   设计文档要求（第6节）：
   - 加载态：aria-busy="true" + 文案变化
   - 空态：role="status" + aria-live="polite" + 恢复方法
   - 错误态：模块内显示 + 多处同步
   - 当前态：aria-current="page"/"true"/"pressed"
   ============================================================ */

import React from 'react'
import { Spin, Empty, Alert, Button, Typography } from 'antd'
import { ReloadOutlined, FilterOutlined, WarningOutlined } from '@ant-design/icons'

const { Text } = Typography

// ═══════════════════════════════════════════════════════════════════════════
// 类型定义
// ═══════════════════════════════════════════════════════════════════════════

export interface StatefulPanelProps {
  /** 加载状态 */
  loading?: boolean
  /** 加载提示文案 */
  loadingText?: string
  /** 空状态 */
  empty?: boolean
  /** 空状态描述 */
  emptyDescription?: string
  /** 空状态恢复操作 */
  emptyAction?: string
  /** 空状态恢复回调 */
  onEmptyAction?: () => void
  /** 错误信息 */
  error?: string | null
  /** 错误标题 */
  errorTitle?: string
  /** 错误恢复操作 */
  errorAction?: string
  /** 错误恢复回调 */
  onErrorAction?: () => void
  /** 子元素（正常状态） */
  children: React.ReactNode
  /** 面板标题（用于无障碍标记） */
  title?: string
  /** 面板ID（用于无障碍标记） */
  panelId?: string
  /** 自定义样式 */
  style?: React.CSSProperties
  /** 自定义类名 */
  className?: string
  /** 最小高度（避免加载时布局抖动） */
  minHeight?: number | string
}

// ═══════════════════════════════════════════════════════════════════════════
// 加载状态
// ═══════════════════════════════════════════════════════════════════════════

const LoadingState: React.FC<{
  text?: string
  title?: string
  panelId?: string
}> = ({ text = '刷新中...', title, panelId }) => (
  <div
    role="status"
    aria-busy="true"
    aria-live="polite"
    aria-label={title ? `${title} - ${text}` : text}
    id={panelId ? `${panelId}-loading` : undefined}
    style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: 200,
      gap: 12,
    }}
  >
    <Spin size="large" />
    <Text type="secondary" style={{ fontSize: 13 }}>
      {text}
    </Text>
  </div>
)

// ═══════════════════════════════════════════════════════════════════════════
// 空状态
// ═══════════════════════════════════════════════════════════════════════════

const EmptyState: React.FC<{
  description?: string
  action?: string
  onAction?: () => void
  title?: string
  panelId?: string
}> = ({
  description = '没有符合条件的数据',
  action = '清除筛选',
  onAction,
  title,
  panelId,
}) => (
  <div
    role="status"
    aria-live="polite"
    aria-label={title ? `${title} - 空状态` : '空状态'}
    id={panelId ? `${panelId}-empty` : undefined}
    style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: 200,
      gap: 16,
    }}
  >
    <Empty
      description={
        <span style={{ color: 'var(--muted)', fontSize: 13 }}>
          {description}
        </span>
      }
      image={Empty.PRESENTED_IMAGE_SIMPLE}
    />
    {onAction && (
      <Button
        type="link"
        icon={<FilterOutlined />}
        onClick={onAction}
        aria-label={action}
        style={{ fontSize: 13 }}
      >
        {action}
      </Button>
    )}
  </div>
)

// ═══════════════════════════════════════════════════════════════════════════
// 错误状态
// ═══════════════════════════════════════════════════════════════════════════

const ErrorState: React.FC<{
  message: string
  title?: string
  action?: string
  onAction?: () => void
  panelTitle?: string
  panelId?: string
}> = ({
  message,
  title = '加载失败',
  action = '重试',
  onAction,
  panelTitle,
  panelId,
}) => (
  <div
    role="alert"
    aria-live="assertive"
    aria-label={panelTitle ? `${panelTitle} - 错误` : '错误'}
    id={panelId ? `${panelId}-error` : undefined}
    style={{
      padding: 16,
    }}
  >
    <Alert
      type="error"
      showIcon
      icon={<WarningOutlined />}
      message={title}
      description={
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <Text style={{ fontSize: 13 }}>{message}</Text>
          {onAction && (
            <Button
              type="primary"
              danger
              icon={<ReloadOutlined />}
              onClick={onAction}
              aria-label={action}
              style={{ marginTop: 8 }}
            >
              {action}
            </Button>
          )}
        </div>
      }
    />
  </div>
)

// ═══════════════════════════════════════════════════════════════════════════
// 主组件
// ═══════════════════════════════════════════════════════════════════════════

export const StatefulPanel: React.FC<StatefulPanelProps> = ({
  loading,
  loadingText,
  empty,
  emptyDescription,
  emptyAction,
  onEmptyAction,
  error,
  errorTitle,
  errorAction,
  onErrorAction,
  children,
  title,
  panelId,
  style,
  className,
  minHeight = 200,
}) => {
  // 优先级：错误 > 加载 > 空 > 正常
  if (error) {
    return (
      <div
        style={{ minHeight, ...style }}
        className={className}
        aria-label={title}
      >
        <ErrorState
          message={error}
          title={errorTitle}
          action={errorAction}
          onAction={onErrorAction}
          panelTitle={title}
          panelId={panelId}
        />
      </div>
    )
  }

  if (loading) {
    return (
      <div
        style={{ minHeight, ...style }}
        className={className}
        aria-label={title}
      >
        <LoadingState
          text={loadingText}
          title={title}
          panelId={panelId}
        />
      </div>
    )
  }

  if (empty) {
    return (
      <div
        style={{ minHeight, ...style }}
        className={className}
        aria-label={title}
      >
        <EmptyState
          description={emptyDescription}
          action={emptyAction}
          onAction={onEmptyAction}
          title={title}
          panelId={panelId}
        />
      </div>
    )
  }

  // 正常状态
  return (
    <div
      style={{ ...style }}
      className={className}
      aria-label={title}
      id={panelId}
      role="region"
    >
      {children}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// 导出便捷钩子
// ═══════════════════════════════════════════════════════════════════════════

export interface AsyncState {
  loading: boolean
  error: string | null
  data: unknown | null
}

export function useAsyncState(): [
  AsyncState,
  {
    setLoading: (loading: boolean) => void
    setError: (error: string | null) => void
    setData: (data: unknown | null) => void
    reset: () => void
  }
] {
  const [state, setState] = React.useState<AsyncState>({
    loading: false,
    error: null,
    data: null,
  })

  const controls = {
    setLoading: (loading: boolean) => setState(prev => ({ ...prev, loading, error: null })),
    setError: (error: string | null) => setState(prev => ({ ...prev, loading: false, error })),
    setData: (data: unknown | null) => setState(prev => ({ ...prev, loading: false, error: null, data })),
    reset: () => setState({ loading: false, error: null, data: null }),
  }

  return [state, controls]
}

// ═══════════════════════════════════════════════════════════════════════════
// 导出
// ═══════════════════════════════════════════════════════════════════════════

export default StatefulPanel