// 拆解架构整合 Step4: 单树视图 (upstream_downstream) + overlay 维度切换
// value_chain/competition 从 method tab 降级为可叠加的 overlay 注解开关,
// 勾选后 chain/deconstruct 调用带 overlays=[...], 标签按 node_id 合并进树节点

import { Checkbox, Space, Tag } from 'antd'
import { ApartmentOutlined, DollarOutlined, TrophyOutlined } from '@ant-design/icons'

/** 拆解方法类型保留: bom 钻取链视图与旧调用仍在用 */
export type ChainMethod = 'upstream_downstream' | 'value_chain' | 'competition'

/** 可叠加的 overlay 注解维度 (后端 OVERLAY_ANNOTATORS 注册表) */
export type ChainOverlay = 'value_chain' | 'competition'

interface OverlayOption {
  value: ChainOverlay
  label: string
  icon: React.ReactNode
  description: string
  tagColor: string
}

const OVERLAY_OPTIONS: OverlayOption[] = [
  {
    value: 'value_chain',
    label: '价值链',
    icon: <DollarOutlined />,
    description: '叠加毛利率/议价权/价值增值标签',
    tagColor: 'green',
  },
  {
    value: 'competition',
    label: '竞争格局',
    icon: <TrophyOutlined />,
    description: '叠加集中度/龙头份额/壁垒/威胁标签',
    tagColor: 'orange',
  },
]

interface MethodSelectorProps {
  overlays: ChainOverlay[]
  onOverlaysChange: (overlays: ChainOverlay[]) => void
  loading?: boolean
  disabled?: boolean
}

export default function MethodSelector({
  overlays,
  onOverlaysChange,
  loading = false,
  disabled = false,
}: MethodSelectorProps) {
  const isDisabled = disabled || loading
  const activeOverlays = OVERLAY_OPTIONS.filter(option => overlays.includes(option.value))

  const toggleOverlay = (overlay: ChainOverlay, checked: boolean) => {
    if (checked) {
      onOverlaysChange([...overlays, overlay])
    } else {
      onOverlaysChange(overlays.filter(item => item !== overlay))
    }
  }

  return (
    <Space direction="vertical" size={8} style={{ width: '100%' }}>
      <Space size={8} wrap>
        <Tag color="blue" icon={<ApartmentOutlined />}>上下游拆解</Tag>
        {OVERLAY_OPTIONS.map(option => (
          <Checkbox
            key={option.value}
            checked={overlays.includes(option.value)}
            disabled={isDisabled}
            onChange={e => toggleOverlay(option.value, e.target.checked)}
          >
            <Space size={4}>
              {option.icon}
              {option.label}
            </Space>
          </Checkbox>
        ))}
      </Space>
      <Space size={6} wrap>
        {activeOverlays.length === 0 ? (
          <span style={{ color: '#666', fontSize: 12 }}>单树视图: 产业链上下游关系拆解, 可勾选 overlay 叠加多维标签</span>
        ) : (
          activeOverlays.map(option => (
            <Tag key={option.value} color={option.tagColor}>{option.description}</Tag>
          ))
        )}
      </Space>
    </Space>
  )
}

export { OVERLAY_OPTIONS }
