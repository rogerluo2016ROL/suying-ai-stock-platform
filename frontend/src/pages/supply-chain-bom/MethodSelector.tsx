// P2-08: Method selector with three view tabs for chain deconstruct
// Supports: upstream_downstream / value_chain / competition

import { Radio, Space, Tag } from 'antd'
import { ApartmentOutlined, DollarOutlined, TrophyOutlined } from '@ant-design/icons'

export type ChainMethod = 'upstream_downstream' | 'value_chain' | 'competition'

interface MethodOption {
  value: ChainMethod
  label: string
  icon: React.ReactNode
  description: string
  tagColor: string
}

const METHOD_OPTIONS: MethodOption[] = [
  {
    value: 'upstream_downstream',
    label: '上下游',
    icon: <ApartmentOutlined />,
    description: '产业链上下游关系拆解',
    tagColor: 'blue',
  },
  {
    value: 'value_chain',
    label: '价值链',
    icon: <DollarOutlined />,
    description: '价值创造与利润分配分析',
    tagColor: 'green',
  },
  {
    value: 'competition',
    label: '竞争格局',
    icon: <TrophyOutlined />,
    description: '市场竞争态势与集中度',
    tagColor: 'orange',
  },
]

interface MethodSelectorProps {
  value: ChainMethod
  onChange: (method: ChainMethod) => void
  loading?: boolean
  disabled?: boolean
}

export default function MethodSelector({
  value,
  onChange,
  loading = false,
  disabled = false,
}: MethodSelectorProps) {
  const currentMethod = METHOD_OPTIONS.find(m => m.value === value)

  return (
    <Space direction="vertical" size={8} style={{ width: '100%' }}>
      <Radio.Group
        value={value}
        onChange={e => onChange(e.target.value as ChainMethod)}
        disabled={disabled || loading}
        buttonStyle="solid"
        size="small"
      >
        {METHOD_OPTIONS.map(option => (
          <Radio.Button key={option.value} value={option.value}>
            <Space size={4}>
              {option.icon}
              {option.label}
            </Space>
          </Radio.Button>
        ))}
      </Radio.Group>
      {currentMethod && (
        <Space size={6}>
          <Tag color={currentMethod.tagColor}>{currentMethod.label}</Tag>
          <span style={{ color: '#666', fontSize: 12 }}>{currentMethod.description}</span>
        </Space>
      )}
    </Space>
  )
}

export { METHOD_OPTIONS }