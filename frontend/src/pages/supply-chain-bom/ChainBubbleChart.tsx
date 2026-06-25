/**
 * 三因子气泡图组件 - ChainBubbleChart
 * Phase 3: 展示候选标的的三因子共振关系
 *
 * 横轴: 政策强度 (0-5)
 * 纵轴: 业绩兑现 (0-20)
 * 大小: 综合评分
 * 颜色: 共振等级 (强启动/启动/观察/观望)
 */

import { useEffect, useRef, useMemo, useState } from 'react'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import { Card, Switch, Space, Typography, Empty, Spin, Tag, Select } from 'antd'
import { BulbOutlined, ReloadOutlined } from '@ant-design/icons'
import {
  buildBubbleOption,
  candidateToBubblePoint,
  type BubbleDataPoint,
} from './chartOptions'
import type { CandidateCompany } from './types'

const { Text, Title } = Typography

export interface ChainBubbleChartProps {
  /** 候选公司数据 */
  candidates: CandidateCompany[]
  /** 加载状态 */
  loading?: boolean
  /** 点击气泡回调 */
  onPointClick?: (candidate: CandidateCompany) => void
  /** 主题ID（用于标题） */
  themeName?: string
  /** 自定义样式 */
  style?: React.CSSProperties
  /** 自定义类名 */
  className?: string
}

/**
 * 三因子气泡图组件
 */
export default function ChainBubbleChart({
  candidates,
  loading = false,
  onPointClick,
  themeName,
  style,
  className,
}: ChainBubbleChartProps) {
  const chartRef = useRef<HTMLDivElement>(null)
  const chartInstance = useRef<echarts.ECharts | null>(null)
  const [darkMode, setDarkMode] = useState(false)
  const [resonanceFilter, setResonanceFilter] = useState<string>('all')

  // 转换候选数据为气泡点
  const bubbleData = useMemo<BubbleDataPoint[]>(() => {
    return candidates.map(candidateToBubblePoint)
  }, [candidates])

  // 根据共振等级筛选
  const filteredData = useMemo<BubbleDataPoint[]>(() => {
    if (resonanceFilter === 'all') return bubbleData
    return bubbleData.filter(point => point.resonanceLevel === resonanceFilter)
  }, [bubbleData, resonanceFilter])

  // 构建ECharts option
  const chartOption = useMemo<EChartsOption>(() => {
    return buildBubbleOption(filteredData, darkMode)
  }, [filteredData, darkMode])

  // 初始化和更新图表
  useEffect(() => {
    if (!chartRef.current || loading) return

    // 初始化图表
    if (!chartInstance.current) {
      chartInstance.current = echarts.init(chartRef.current)
    }

    // 设置option
    chartInstance.current.setOption(chartOption, { notMerge: true })

    // 点击事件
    chartInstance.current.on('click', (params: any) => {
      if (params.data?.code && onPointClick) {
        const candidate = candidates.find(c => c.code === params.data.code)
        if (candidate) onPointClick(candidate)
      }
    })

    // 窗口大小变化时resize
    const handleResize = () => {
      chartInstance.current?.resize()
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
    }
  }, [chartOption, loading, candidates, onPointClick])

  // 清理图表实例
  useEffect(() => {
    return () => {
      chartInstance.current?.dispose()
      chartInstance.current = null
    }
  }, [])

  // 暗色模式切换时resize
  useEffect(() => {
    chartInstance.current?.resize()
  }, [darkMode])

  // 统计各共振等级数量
  const resonanceStats = useMemo(() => {
    const stats: Record<string, number> = { 强启动: 0, 启动: 0, 观察: 0, 观望: 0 }
    bubbleData.forEach(point => {
      stats[point.resonanceLevel]++
    })
    return stats
  }, [bubbleData])

  // 手动刷新图表
  const handleRefresh = () => {
    if (chartInstance.current) {
      chartInstance.current.clear()
      chartInstance.current.setOption(chartOption)
    }
  }

  return (
    <Card
      title={
        <Space>
          <span>{themeName ? `${themeName} - 三因子共振图` : '三因子共振气泡图'}</span>
          {bubbleData.length > 0 && (
            <Tag color="blue">{filteredData.length}/{bubbleData.length} 标的</Tag>
          )}
        </Space>
      }
      extra={
        <Space size="small">
          <Select
            size="small"
            value={resonanceFilter}
            onChange={setResonanceFilter}
            style={{ width: 100 }}
            options={[
              { label: '全部', value: 'all' },
              { label: '强启动', value: '强启动' },
              { label: '启动', value: '启动' },
              { label: '观察', value: '观察' },
              { label: '观望', value: '观望' },
            ]}
          />
          <Switch
            size="small"
            checked={darkMode}
            onChange={setDarkMode}
            checkedChildren={<BulbOutlined />}
            unCheckedChildren={<BulbOutlined />}
          />
          <ReloadOutlined
            style={{ cursor: 'pointer', color: '#666' }}
            onClick={handleRefresh}
            title="刷新图表"
          />
        </Space>
      }
      style={style}
      className={className}
      styles={{
        body: { padding: '12px 16px', minHeight: 300 },
      }}
    >
      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 300 }}>
          <Spin tip="加载中..." />
        </div>
      ) : bubbleData.length === 0 ? (
        <Empty
          description="暂无候选数据"
          style={{ margin: '40px 0' }}
        />
      ) : (
        <>
          {/* 共振等级统计 */}
          <div style={{ marginBottom: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {Object.entries(resonanceStats).map(([level, count]) => (
              count > 0 && (
                <Tag
                  key={level}
                  color={
                    level === '强启动' ? 'red'
                    : level === '启动' ? 'orange'
                    : level === '观察' ? 'blue'
                    : 'default'
                  }
                >
                  {level}: {count}
                </Tag>
              )
            ))}
          </div>

          {/* ECharts容器 */}
          <div
            ref={chartRef}
            style={{
              width: '100%',
              height: 400,
              borderRadius: 4,
            }}
          />

          {/* 图表说明 */}
          <div style={{ marginTop: 8, fontSize: 12, color: '#666' }}>
            <Text type="secondary">
              提示: 气泡大小 = 综合评分，颜色 = 共振等级（强启动=红色，启动=橙色，观察=蓝色，观望=灰色）。
              点击气泡查看详情。
            </Text>
          </div>
        </>
      )}
    </Card>
  )
}