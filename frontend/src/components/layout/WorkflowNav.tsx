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
import { useNavigate } from 'react-router-dom'
import { CheckCircleOutlined, ClockCircleOutlined, RightOutlined } from '@ant-design/icons'

// ═══════════════════════════════════════════════════════════════════════════
// 类型定义
// ═══════════════════════════════════════════════════════════════════════════

export interface WorkflowStep {
  key: string
  label: string
  description?: string
  path?: string
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
    <nav className="workflow-nav" aria-label="P0 主链路">
      <div className="workflow-track">
        {steps.map((step, index) => {
          const isActive = step.key === currentStep
          const isCompleted = step.status === 'completed'
          const isPending = step.status === 'pending'

          return (
            <React.Fragment key={step.key}>
              <button
                type="button"
                className={`workflow-step${isActive ? ' active' : ''}${isCompleted ? ' completed' : ''}`}
                onClick={() => onStepChange?.(step.key)}
                aria-current={isActive ? 'step' : undefined}
              >
                <span className="workflow-index">
                  {isCompleted && <CheckCircleOutlined />}
                  {isPending && <ClockCircleOutlined />}
                  {!isCompleted && !isPending && String(index + 1).padStart(2, '0')}
                </span>
                <span className="workflow-copy">
                  <span className="workflow-label">{step.label}</span>
                  {step.description && <span className="workflow-desc">{step.description}</span>}
                </span>
              </button>
              {index < steps.length - 1 && <RightOutlined className="workflow-arrow" aria-hidden="true" />}
            </React.Fragment>
          )
        })}
      </div>
    </nav>
  )
}

export const P0_WORKFLOW_STEPS: WorkflowStep[] = [
  { key: 'candidate', label: '候选池', description: '模型选股', path: '/screener' },
  { key: 'plan', label: '方案管理', description: '组合计划', path: '/strategy' },
  { key: 'order', label: '下单面板', description: '订单草稿', path: '/trade' },
  { key: 'risk', label: '风控闸门', description: '放行/拦截', path: '/trade/risk-verdicts' },
  { key: 'review', label: '回测复盘', description: '交易复核', path: '/backtest' },
]

export interface P0WorkflowNavProps {
  currentStep: 'candidate' | 'plan' | 'order' | 'risk' | 'review'
}

export const P0WorkflowNav: React.FC<P0WorkflowNavProps> = ({ currentStep }) => {
  const navigate = useNavigate()
  const currentIndex = P0_WORKFLOW_STEPS.findIndex(step => step.key === currentStep)
  const steps = P0_WORKFLOW_STEPS.map((step, index) => ({
    ...step,
    status: index < currentIndex ? 'completed' : step.key === currentStep ? 'active' : 'pending',
  })) as WorkflowStep[]

  return (
    <WorkflowNav
      steps={steps}
      currentStep={currentStep}
      onStepChange={(stepKey) => {
        const step = P0_WORKFLOW_STEPS.find(item => item.key === stepKey)
        if (step?.path) navigate(step.path)
      }}
    />
  )
}

export default WorkflowNav
