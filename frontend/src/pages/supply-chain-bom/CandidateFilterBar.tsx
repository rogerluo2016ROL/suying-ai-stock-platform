// Phase 3: Candidate filter bar for chain candidates V6 resonance scoring
// Supports filter types and resonance_level selection

import { Select, Space, Tag, Typography } from 'antd'
import { FilterOutlined, SignalFilled } from '@ant-design/icons'
import {
  chainApi,
  type ChainCandidateFilter,
  type ResonanceLevel,
  type ChainCandidatesResponse,
  type ChainCandidate,
  type FilterSummary,
  type ResonanceSummary,
} from '../../api/client'
import { useState, useEffect, useCallback } from 'react'

const { Text } = Typography

/** Filter type options for Select component */
const FILTER_OPTIONS: Array<{
  value: ChainCandidateFilter
  label: string
  description: string
  tagColor: string
}> = [
  {
    value: 'high_growth',
    label: '高增长',
    description: '业绩增速 ≥50%',
    tagColor: 'green',
  },
  {
    value: 'high_profit',
    label: '高利润',
    description: '毛利率 ≥50%',
    tagColor: 'gold',
  },
  {
    value: 'high_moat',
    label: '高壁垒',
    description: 'chokepoint ≥6',
    tagColor: 'purple',
  },
  {
    value: 'chokepoint_core',
    label: '卡脖子核心',
    description: '国产替代关键',
    tagColor: 'red',
  },
  {
    value: 'all',
    label: '全部',
    description: '无筛选',
    tagColor: 'blue',
  },
]

/** Resonance level options for Select component */
const RESONANCE_OPTIONS: Array<{
  value: ResonanceLevel
  label: string
  description: string
  tagColor: string
}> = [
  {
    value: '强启动',
    label: '强启动',
    description: '3因子全部达标',
    tagColor: 'red',
  },
  {
    value: '启动',
    label: '启动',
    description: '2因子达标',
    tagColor: 'orange',
  },
  {
    value: '关注',
    label: '关注',
    description: '1因子达标',
    tagColor: 'blue',
  },
  {
    value: '观察',
    label: '观察',
    description: '默认观察',
    tagColor: 'default',
  },
]

interface CandidateFilterBarProps {
  /** Callback when candidates are fetched */
  onCandidatesChange: (candidates: ChainCandidate[]) => void
  /** Callback when loading state changes */
  onLoadingChange?: (loading: boolean) => void
  /** Callback when summary stats change */
  onSummaryChange?: (filterSummary: FilterSummary, resonanceSummary: ResonanceSummary) => void
  /** Initial filter value */
  defaultFilter?: ChainCandidateFilter
  /** Initial resonance level */
  defaultResonanceLevel?: ResonanceLevel
  /** Top N candidates to fetch */
  topN?: number
  /** Trade date filter */
  tradeDate?: string
  /** Disabled state */
  disabled?: boolean
}

export default function CandidateFilterBar({
  onCandidatesChange,
  onLoadingChange,
  onSummaryChange,
  defaultFilter = 'all',
  defaultResonanceLevel,
  topN = 30,
  tradeDate,
  disabled = false,
}: CandidateFilterBarProps) {
  const [filter, setFilter] = useState<ChainCandidateFilter>(defaultFilter)
  const [resonanceLevel, setResonanceLevel] = useState<ResonanceLevel | undefined>(defaultResonanceLevel)
  const [loading, setLoading] = useState(false)
  const [totalCount, setTotalCount] = useState(0)
  const [elapsedMs, setElapsedMs] = useState(0)
  const [lastFilterSummary, setLastFilterSummary] = useState<FilterSummary | null>(null)
  const [lastResonanceSummary, setLastResonanceSummary] = useState<ResonanceSummary | null>(null)

  /** Fetch candidates from API */
  const fetchCandidates = useCallback(async () => {
    setLoading(true)
    onLoadingChange?.(true)
    try {
      const response = await chainApi.getCandidates({
        filter,
        resonance_level: resonanceLevel,
        top_n: topN,
        trade_date: tradeDate,
      })
      const data = response.data as ChainCandidatesResponse
      onCandidatesChange(data.candidates)
      setTotalCount(data.total_count)
      setElapsedMs(data.elapsed_ms)
      setLastFilterSummary(data.filter_summary as unknown as FilterSummary)
      setLastResonanceSummary(data.resonance_summary as unknown as ResonanceSummary)
      onSummaryChange?.(data.filter_summary as unknown as FilterSummary, data.resonance_summary as unknown as ResonanceSummary)
    } catch (error) {
      console.error('Failed to fetch chain candidates:', error)
      onCandidatesChange([])
      setTotalCount(0)
    } finally {
      setLoading(false)
      onLoadingChange?.(false)
    }
  }, [filter, resonanceLevel, topN, tradeDate, onCandidatesChange, onLoadingChange, onSummaryChange])

  /** Fetch candidates on filter/resonance change */
  useEffect(() => {
    fetchCandidates()
  }, [fetchCandidates])

  /** Current filter option metadata */
  const currentFilterOption = FILTER_OPTIONS.find(opt => opt.value === filter)
  const currentResonanceOption = resonanceLevel
    ? RESONANCE_OPTIONS.find(opt => opt.value === resonanceLevel)
    : null

  return (
    <div style={{ padding: '12px 16px', background: '#fafafa', borderRadius: 8, marginBottom: 12 }}>
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Space wrap size={8} align="center" style={{ justifyContent: 'space-between', width: '100%' }}>
          <Space wrap size={8} align="center">
            <FilterOutlined style={{ color: '#666' }} />
            <Select<ChainCandidateFilter>
              value={filter}
              onChange={setFilter}
              disabled={disabled || loading}
              style={{ width: 140 }}
              placeholder="筛选类型"
              options={FILTER_OPTIONS.map(opt => ({
                value: opt.value,
                label: (
                  <Space size={4}>
                    <Tag color={opt.tagColor} style={{ marginRight: 0 }}>{opt.label}</Tag>
                  </Space>
                ),
              }))}
            />
            <SignalFilled style={{ color: '#666' }} />
            <Select<ResonanceLevel>
              value={resonanceLevel}
              onChange={setResonanceLevel}
              disabled={disabled || loading}
              style={{ width: 140 }}
              placeholder="共振等级"
              allowClear
              options={RESONANCE_OPTIONS.map(opt => ({
                value: opt.value,
                label: (
                  <Space size={4}>
                    <Tag color={opt.tagColor} style={{ marginRight: 0 }}>{opt.label}</Tag>
                  </Space>
                ),
              }))}
            />
          </Space>
          <Space size={8}>
            <Tag color="blue">{totalCount} 候选</Tag>
            <Text type="secondary">{elapsedMs}ms</Text>
          </Space>
        </Space>
        {currentFilterOption && (
          <Space size={6}>
            <Tag color={currentFilterOption.tagColor}>{currentFilterOption.label}</Tag>
            <Text type="secondary">{currentFilterOption.description}</Text>
            {lastFilterSummary && (
              <Text type="secondary">
                (池: {lastFilterSummary[filter]}个)
              </Text>
            )}
          </Space>
        )}
        {currentResonanceOption && resonanceLevel && (
          <Space size={6}>
            <Tag color={currentResonanceOption.tagColor}>{currentResonanceOption.label}</Tag>
            <Text type="secondary">{currentResonanceOption.description}</Text>
            {lastResonanceSummary && (
              <Text type="secondary">
                (池: {lastResonanceSummary[resonanceLevel]}个)
              </Text>
            )}
          </Space>
        )}
      </Space>
    </div>
  )
}

/** Export filter/resonance options for reuse */
export { FILTER_OPTIONS, RESONANCE_OPTIONS }