// 拆解架构整合 Step4: 树节点 overlay 标签渲染
// transmission_layer 小标签常显; value_chain/competition 标签随 overlay 开关叠加

import { Space, Tag, Tooltip } from 'antd'
import type { BomNode } from './types'
import type { ChainOverlay } from './MethodSelector'

interface NodeOverlayTagsProps {
  node: Pick<BomNode, 'transmission_layer_name' | 'value_chain' | 'competition'>
  overlays: ChainOverlay[]
}

function formatPct(value: number | null | undefined): string | null {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return null
  return `${Number(value).toFixed(0)}%`
}

function formatRaw(value: number | null | undefined): string | null {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return null
  return `${Number(value)}`
}

export default function NodeOverlayTags({ node, overlays }: NodeOverlayTagsProps) {
  const tags: React.ReactNode[] = []

  if (node.transmission_layer_name) {
    tags.push(
      <Tag key="transmission" color="cyan" style={{ fontSize: 11 }}>
        {node.transmission_layer_name}
      </Tag>,
    )
  }

  if (overlays.includes('value_chain') && node.value_chain) {
    const vc = node.value_chain
    const parts = [
      formatPct(vc.margin) && `毛利 ${formatPct(vc.margin)}`,
      formatRaw(vc.pricing_power) && `议价权 ${formatRaw(vc.pricing_power)}`,
      formatPct(vc.value_added) && `增值 ${formatPct(vc.value_added)}`,
    ].filter(Boolean)
    if (parts.length > 0) {
      tags.push(
        <Tooltip key="value_chain" title={vc.note}>
          <Tag color="green" style={{ fontSize: 11 }}>{parts.join(' · ')}</Tag>
        </Tooltip>,
      )
    }
  }

  if (overlays.includes('competition') && node.competition) {
    const comp = node.competition
    const parts = [
      formatPct(comp.concentration) && `集中度 ${formatPct(comp.concentration)}`,
      formatPct(comp.leader_share) && `龙头 ${formatPct(comp.leader_share)}`,
      formatRaw(comp.barrier) && `壁垒 ${formatRaw(comp.barrier)}`,
      formatRaw(comp.threat) && `威胁 ${formatRaw(comp.threat)}`,
    ].filter(Boolean)
    if (parts.length > 0) {
      tags.push(
        <Tooltip key="competition" title={comp.note}>
          <Tag color="orange" style={{ fontSize: 11 }}>{parts.join(' · ')}</Tag>
        </Tooltip>,
      )
    }
  }

  if (tags.length === 0) return null
  return <Space size={4} wrap>{tags}</Space>
}
