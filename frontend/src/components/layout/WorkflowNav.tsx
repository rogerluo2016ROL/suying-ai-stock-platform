/* ============================================================
   速赢AI — 顶部工作流导航组件

   来源：docs/design/new front/design-spec.md 第3.2节
   用途：顶部横向菜单负责页面内业务流程

   设计规范：
   - 高度：40px
   - 背景：var(--surface-2)
   - 当前步骤：aria-current="step"
   - 导航项间距：8px
   ============================================================ */

import React from 'react'
import { Space, Button, Typography } from 'antd'
import { CheckCircleOutlined, ClockCircleOutlined } from '@ant-design/icons'

const { Text } = Typography

// ═══════════════════════════════════════════════════════════════════════════
// 类型定义
// ═══════════════════════════════════════════════════════════════════════════

export interface WorkflowStep {
  key: string
  label: string
  status?: 'pending' | 'active' | 'completed'
}

export interface WorkflowNavProps {
  steps: WorkflowStep[]
  currentStep: string
  onStepChange?: (stepKey: string) => void
}

// ═══════════════════════════════════════════════════════════════════════════
// 组件
// ═══════════════════════════════════════════════════════════════════════════

export const WorkflowNav: React.FC<WorkflowNavProps> = ({
  steps,
  currentStep,
  onStepChange,
}) => {
  return (
    <div
      style={{
        height: 40,
        display: 'flex',
        alignItems: 'center',
        padding: '0 16px',
        background: 'var(--surface-2)',
        borderBottom: '1px solid var(--border)',
      }}
    >
      <Space size={8}>
        {steps.map((step, index) => {
          const isActive = step.key === currentStep
          const isCompleted = step.status === 'completed'
          const isPending = step.status === 'pending'

          return (
            <Button
              key={step.key}
              type="text"
              size="small"
              onClick={() => onStepChange?.(step.key)}
              aria-current={isActive ? 'step' : undefined}
              style={{
                height: 32,
                padding: '4px 12px',
                borderRadius: 'var(--radius-sm)',
                background: isActive ? 'var(--accent-dim)' : 'transparent',
                color: isActive ? 'var(--accent)' : isCompleted ? 'var(--down)' : 'var(--muted)',
                fontWeight: isActive ? 600 : 400,
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              {/* 状态图标 */}
              {isCompleted && <CheckCircleOutlined style={{ fontSize: 12 }} />}
              {isPending && <ClockCircleOutlined style={{ fontSize: 12 }} />}

              {/* 步骤编号 */}
              <Text
                style={{
                  fontSize: 11,
                  color: isActive ? 'var(--accent)' : 'var(--muted)',
                }}
              >
                {index + 1}.
              </Text>

              {/* 步骤名称 */}
              <Text
                style={{
                  fontSize: 13,
                  color: isActive ? 'var(--accent)' : isCompleted ? 'var(--fg)' : 'var(--fg-2)',
                }}
              >
                {step.label}
              </Text>
            </Button>
          )
        })}
      </Space>
    </div>
  )
}

export default WorkflowNav