// 产业链解构主视图：BOM层层拆解（左）+ 单树拓扑与 overlay 维度图（中）+ 选股模型（右）
// 从 SupplyChainBom.tsx 拆出，图表 option 与列定义随 UI 一起下沉

import { useMemo } from 'react'
import { Button, Col, Row, Space, Statistic, Table, Tag, Typography } from 'antd'
import { ApartmentOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import type { ChainDeconstructResponse } from '../../api/client'
import type { SupplyChainNode } from '../../api/types'
import ChainTreeChart from './ChainTreeChart'
import MethodSelector, { type ChainOverlay } from './MethodSelector'
import type { BomNode, ThemeRow, WorkbenchModel } from './types'
import { chainMethodSummary } from './helpers'
import { formatNumber } from './formatters'
import { lightTokens, alpha } from '../../styles/tokens'

const { Title, Text, Paragraph } = Typography

/** accent 半透明叠色（echarts bar/scatter 用，token 派生自 lightTokens.accent #3d8bff） */
const ACCENT_OVERLAY = alpha.accent(0.45)
const ACCENT_OVERLAY_SOFT = alpha.accent(0.28)

// 主视图固定 upstream_downstream 单树，method summary 为常量
const METHOD_SUMMARY = chainMethodSummary('upstream_downstream')

interface ChainDeconstructSectionProps {
  themes: ThemeRow[]
  nodes: BomNode[]
  edges: any[]
  filteredNodes: BomNode[]
  selectedThemeId: string
  selectedNodeId: string
  selectedTheme?: ThemeRow
  model: WorkbenchModel
  nodeDetail: any
  activeCandidateCount: number
  chainOverlays: ChainOverlay[]
  chainLoading: boolean
  chainDeconstructResult: ChainDeconstructResponse | null
  loading: boolean
  onSelectTheme: (themeId: string) => void
  onSelectNode: (node: BomNode) => void
  onOverlaysChange: (overlays: ChainOverlay[]) => void
}

export default function ChainDeconstructSection({
  themes,
  nodes,
  edges,
  filteredNodes,
  selectedThemeId,
  selectedNodeId,
  selectedTheme,
  model,
  nodeDetail,
  activeCandidateCount,
  chainOverlays,
  chainLoading,
  chainDeconstructResult,
  loading,
  onSelectTheme,
  onSelectNode,
  onOverlaysChange,
}: ChainDeconstructSectionProps) {
  const themeColumns: any[] = [
    {
      title: '政策主题',
      dataIndex: 'name',
      render: (_: string, row: ThemeRow) => (
        <Button type="link" icon={<ApartmentOutlined />} onClick={() => onSelectTheme(row.theme_id)}>
          {row.name}
        </Button>
      ),
    },
    { title: '权重', dataIndex: 'policy_weight', width: 76, render: (v: number) => formatNumber(v, 2) },
    { title: '节点', dataIndex: 'node_count', width: 68 },
  ]

  const graphOption = useMemo(() => {
    const nodePalette = [lightTokens.accent, lightTokens.down, lightTokens.muted]
    const graphNodes = filteredNodes.map((node, index) => ({
      id: node.node_id,
      name: node.name,
      value: node.policy_theme,
      symbolSize: selectedNodeId === node.node_id ? 62 : 48,
      x: Math.cos((index / Math.max(1, filteredNodes.length)) * Math.PI * 2) * 180,
      y: Math.sin((index / Math.max(1, filteredNodes.length)) * Math.PI * 2) * 120,
      itemStyle: {
        color: selectedNodeId === node.node_id ? lightTokens.up : nodePalette[index % 3],
      },
      label: { show: true, formatter: '{b}' },
    }))
    const nodeIds = new Set(graphNodes.map(node => node.id))
    const graphEdges = edges
      .filter(edge => nodeIds.has(edge.from_node_id) && nodeIds.has(edge.to_node_id))
      .map(edge => ({ source: edge.from_node_id, target: edge.to_node_id, name: edge.relation }))
    return {
      tooltip: { trigger: 'item' },
      series: [{
        type: 'graph',
        layout: 'none',
        roam: true,
        data: graphNodes,
        links: graphEdges,
        edgeSymbol: ['none', 'arrow'],
        lineStyle: { color: lightTokens.muted, width: 1.2 },
        label: { color: lightTokens.fg, fontSize: 12 },
      }],
    }
  }, [edges, filteredNodes, selectedNodeId])

  /** 4.2：从 chainDeconstructResult.tree（SupplyChainNode）收集叶子节点，供 value/competition 图 */
  const chainLeaves = useMemo<SupplyChainNode[]>(() => {
    const tree = chainDeconstructResult?.tree as SupplyChainNode | undefined
    if (!tree) return []
    const out: SupplyChainNode[] = []
    const walk = (node: SupplyChainNode) => {
      if (node.children && node.children.length > 0) {
        node.children.forEach(walk)
      } else {
        out.push(node)
      }
    }
    walk(tree)
    return out
  }, [chainDeconstructResult])

  /** 4.2 value_chain 模式：毛利率/价值增值横向对比 bar（对齐 preview valueChart） */
  const valueChainOption = useMemo(() => {
    const rows = chainLeaves.length > 0 ? chainLeaves : []
    return {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: 88, right: 70, top: 24, bottom: 32 },
      xAxis: {
        type: 'value',
        name: '毛利率(%)',
        max: 60,
        axisLabel: { color: lightTokens.muted },
        axisLine: { lineStyle: { color: lightTokens.border } },
        splitLine: { lineStyle: { color: lightTokens.border, type: 'dashed' } },
      },
      yAxis: {
        type: 'category',
        inverse: true,
        data: rows.map(node => node.name),
        axisLabel: { color: lightTokens.fg2, fontWeight: 650 },
        axisLine: { lineStyle: { color: lightTokens.border } },
      },
      series: [
        {
          name: '毛利率',
          type: 'bar',
          barWidth: 22,
          data: rows.map(node => node.value_chain?.margin ?? 0),
          itemStyle: { color: lightTokens.accent, borderRadius: [0, 5, 5, 0] },
          label: { show: true, position: 'right', formatter: '{c}%', color: lightTokens.fg2, fontWeight: 700 },
        },
        {
          name: '价值增值',
          type: 'bar',
          barWidth: 10,
          barGap: '-72%',
          data: rows.map(node => node.value_chain?.value_added ?? 0),
          itemStyle: { color: ACCENT_OVERLAY, borderRadius: [0, 4, 4, 0] },
        },
      ],
    }
  }, [chainLeaves])

  /** 4.2 competition 模式：市场份额 × 议价权 × 候选数气泡图（对齐 preview competitionChart） */
  const competitionOption = useMemo(() => {
    const rows = chainLeaves
    return {
      tooltip: {
        formatter: (p: any) => {
          const n = rows[p.dataIndex]
          if (!n) return ''
          return `${n.name}<br/>议价权: ${n.value_chain?.pricing_power ?? '--'}<br/>价值增值: ${n.value_chain?.value_added ?? '--'}`
        },
      },
      grid: { left: 60, right: 36, top: 36, bottom: 50 },
      xAxis: {
        name: '议价权',
        max: 100,
        axisLabel: { color: lightTokens.muted },
        nameTextStyle: { color: lightTokens.muted },
        splitLine: { lineStyle: { color: lightTokens.border, type: 'dashed' } },
      },
      yAxis: {
        name: '价值增值(%)',
        max: 100,
        axisLabel: { color: lightTokens.muted },
        nameTextStyle: { color: lightTokens.muted },
        splitLine: { lineStyle: { color: lightTokens.border, type: 'dashed' } },
      },
      series: [{
        type: 'scatter',
        data: rows.map(node => {
          const cap = Math.max(8, (node.value_chain?.value_added ?? 10) * 1.2)
          return {
            name: node.name,
            value: [node.value_chain?.pricing_power ?? 0, node.value_chain?.value_added ?? 0, cap],
            symbolSize: Math.max(28, Math.min(80, cap)),
            itemStyle: { color: ACCENT_OVERLAY_SOFT, borderColor: lightTokens.accent, borderWidth: 2 },
            label: { show: true, formatter: '{b}', color: lightTokens.fg2, fontSize: 10, fontWeight: 700 },
          }
        }),
        emphasis: { scale: 1.16 },
      }],
    }
  }, [chainLeaves])

  return (
    <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
      <Col xs={24} lg={7}>
        <div style={{ border: `1px solid ${lightTokens.border}`, borderRadius: lightTokens.radius, background: lightTokens.surface, padding: 12, minHeight: 360 }}>
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Title level={5} style={{ margin: 0 }}>BOM层层拆解</Title>
            {/* P2-09: Use ChainTreeChart instead of Antd Tree */}
            <ChainTreeChart
              themes={themes}
              nodes={nodes}
              selectedThemeId={selectedThemeId}
              selectedNodeId={selectedNodeId}
              onNodeClick={onSelectNode}
              onThemeClick={theme => onSelectTheme(theme.theme_id)}
              height={280}
            />
            <Table
              loading={loading}
              rowKey="theme_id"
              size="small"
              columns={themeColumns}
              dataSource={themes}
              pagination={false}
              rowClassName={row => row.theme_id === selectedThemeId ? 'ant-table-row-selected' : ''}
            />
          </Space>
        </div>
      </Col>

      <Col xs={24} lg={10}>
        <div style={{ minHeight: 360, border: `1px solid ${lightTokens.border}`, borderRadius: lightTokens.radius, background: lightTokens.surface }}>
          {/* Step4: 单树视图 + overlay 维度开关 */}
          <div style={{ padding: '8px 12px', borderBottom: `1px solid ${lightTokens.border}` }}>
            <MethodSelector
              overlays={chainOverlays}
              onOverlaysChange={onOverlaysChange}
              loading={chainLoading}
              disabled={!selectedThemeId}
            />
          </div>
          {/* 主视图固定为上下游拓扑图; overlay 勾选后在下方叠加对应维度图 */}
          <ReactECharts
            option={graphOption}
            style={{ height: 214 }}
            onEvents={{
              click: (params: any) => {
                const nextNode = nodes.find(node => node.node_id === params?.data?.id)
                if (nextNode) onSelectNode(nextNode)
              },
            }}
          />
          {chainOverlays.includes('value_chain') && (
            <ReactECharts option={valueChainOption} style={{ height: 214 }} />
          )}
          {chainOverlays.includes('competition') && (
            <ReactECharts option={competitionOption} style={{ height: 214 }} />
          )}
          {filteredNodes.length === 0 && (
            <div style={{ padding: 24, textAlign: 'center', color: lightTokens.muted, fontSize: 12 }}>
              暂无该主题的拆解节点，切换主题或等待 chain-service 返回。
            </div>
          )}
          <div style={{ borderTop: `1px solid ${lightTokens.border}`, padding: '10px 12px' }}>
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Space align="baseline" style={{ justifyContent: 'space-between', width: '100%' }}>
                <Text strong>{METHOD_SUMMARY.title}</Text>
                <Space size={4}>
                  {chainOverlays.includes('value_chain') && <Tag color="green">价值链</Tag>}
                  {chainOverlays.includes('competition') && <Tag color="orange">竞争格局</Tag>}
                  <Tag color="blue">
                    {chainLoading ? '加载中' : '单树视图'}
                  </Tag>
                </Space>
              </Space>
              <Text type="secondary" style={{ fontSize: 12 }}>{METHOD_SUMMARY.desc}</Text>
              {/* 4.2 mode-note：overlay 三卡注释（对齐 preview mode-note，随开关叠加） */}
              {chainOverlays.includes('value_chain') && (
                <Row gutter={8}>
                  {[['最高毛利环节', '核心零部件', '技术壁垒最高，国产替代难度最大。'], ['利润兑现', '设备制造', '订单和业绩兑现最直接，是从政策受益走向利润兑现的核心环节。'], ['低毛利环节', '封装测试', '毛利率最低，受先进封装投资周期带动。']].map(([label, value, sub]) => (
                    <Col span={8} key={label as string}>
                      <div style={{ background: lightTokens.surface2, border: `1px solid ${lightTokens.border}`, borderRadius: 7, padding: '8px 10px' }}>
                        <div style={{ fontSize: 10, color: lightTokens.muted, marginBottom: 4 }}>{label}</div>
                        <div style={{ fontSize: 13, fontWeight: 700, color: lightTokens.fg }}>{value}</div>
                        <div style={{ fontSize: 10, color: lightTokens.fg2, marginTop: 2, lineHeight: 1.5 }}>{sub}</div>
                      </div>
                    </Col>
                  ))}
                </Row>
              )}
              {chainOverlays.includes('competition') && (
                <Row gutter={8}>
                  {[['寡头垄断', '光刻系统', '全球极高集中度，A股通过光刻胶/光学元件/配套设备参与。'], ['国产突破', '刻蚀/PVD', '进入高壁垒高成长象限，订单兑现与扩产节奏最关键。'], ['分散竞争', '清洗/检测', '国产化率较高，按订单和利润率筛选。']].map(([label, value, sub]) => (
                    <Col span={8} key={label as string}>
                      <div style={{ background: lightTokens.surface2, border: `1px solid ${lightTokens.border}`, borderRadius: 7, padding: '8px 10px' }}>
                        <div style={{ fontSize: 10, color: lightTokens.muted, marginBottom: 4 }}>{label}</div>
                        <div style={{ fontSize: 13, fontWeight: 700, color: lightTokens.fg }}>{value}</div>
                        <div style={{ fontSize: 10, color: lightTokens.fg2, marginTop: 2, lineHeight: 1.5 }}>{sub}</div>
                      </div>
                    </Col>
                  ))}
                </Row>
              )}
              <Row gutter={8}>
                {METHOD_SUMMARY.stats.map(([label, value]) => (
                  <Col span={8} key={label}>
                    <div style={{ background: lightTokens.surface2, border: `1px solid ${lightTokens.elevated}`, borderRadius: 6, padding: 8 }}>
                      <div style={{ fontSize: 11, color: lightTokens.muted }}>{label}</div>
                      <div style={{ fontSize: 12, fontWeight: 700, color: lightTokens.fg }}>{value}</div>
                    </div>
                  </Col>
                ))}
                {METHOD_SUMMARY.stats.length === 0 && (
                  <Col span={24}>
                    <Text type="secondary" style={{ fontSize: 12 }}>上下游图展示节点拓扑，点击节点下钻候选公司。</Text>
                  </Col>
                )}
              </Row>
            </Space>
          </div>
        </div>
      </Col>

      <Col xs={24} lg={7}>
        <div style={{ border: `1px solid ${lightTokens.border}`, borderRadius: lightTokens.radius, background: lightTokens.surface, padding: 16, minHeight: 360 }}>
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Title level={5} style={{ margin: 0 }}>选股模型</Title>
            <Paragraph type="secondary" style={{ marginBottom: 0 }}>
              {model.philosophy || '政策主题定方向，BOM拆解定环节，候选公司池定标的，共振信息定研究信号。'}
            </Paragraph>
            {selectedTheme?.interpretation && (
              <Paragraph style={{ marginBottom: 0 }}>
                {selectedTheme.interpretation}
              </Paragraph>
            )}
            {selectedTheme?.strategic_logic && (
              <Text type="secondary">{selectedTheme.strategic_logic}</Text>
            )}
            {!!selectedTheme?.bom_focus?.length && (
              <Space wrap>
                {selectedTheme.bom_focus.map(item => <Tag key={item} color="cyan">{item}</Tag>)}
              </Space>
            )}
            {!!selectedTheme?.evidence_focus?.length && (
              <Space wrap>
                {selectedTheme.evidence_focus.map(item => <Tag key={item}>{item}</Tag>)}
              </Space>
            )}
            <Row gutter={12}>
              <Col span={8}><Statistic title="候选公司" value={activeCandidateCount} /></Col>
              <Col span={8}><Statistic title="BOM节点" value={nodes.length} /></Col>
              <Col span={8}><Statistic title="证据" value={nodeDetail?.evidence?.length || 0} /></Col>
            </Row>
            <Space wrap>
              {(model.score_dimensions || []).map(item => (
                <Tag key={item.key} color={item.key === 'commercialization' ? 'green' : 'processing'}>
                  <span>{item.name}</span>
                  <Text style={{ marginLeft: 4 }}>{item.weight}</Text>
                </Tag>
              ))}
            </Space>
          </Space>
        </div>
      </Col>
    </Row>
  )
}
