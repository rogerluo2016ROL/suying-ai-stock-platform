/**
 * Unit tests for ChainBubbleChart - buildBubbleOption
 * Testing AC-1 through AC-5 from Task #4
 */

import { describe, it, expect } from 'vitest'
import {
  buildBubbleOption,
  candidateToBubblePoint,
  type BubbleDataPoint,
} from '../pages/supply-chain-bom/chartOptions'
import type { CandidateCompany } from '../pages/supply-chain-bom/types'

describe('buildBubbleOption', () => {
  // Sample bubble data for testing
  const sampleData: BubbleDataPoint[] = [
    {
      code: '600001',
      name: '测试公司A',
      policyIntensity: 4,
      performanceProof: 15,
      score: 18,
      resonanceLevel: '强启动',
      resonanceValue: 3,
      industry: '半导体',
      chokepointScore: 18,
    },
    {
      code: '600002',
      name: '测试公司B',
      policyIntensity: 3,
      performanceProof: 10,
      score: 12,
      resonanceLevel: '启动',
      resonanceValue: 2,
      industry: '元器件',
    },
    {
      code: '600003',
      name: '测试公司C',
      policyIntensity: 2,
      performanceProof: 5,
      score: 8,
      resonanceLevel: '观察',
      resonanceValue: 1,
      industry: 'IT设备',
    },
    {
      code: '600004',
      name: '测试公司D',
      policyIntensity: 0,
      performanceProof: 0,
      score: 3,
      resonanceLevel: '观望',
      resonanceValue: 0,
      industry: '其他',
    },
  ]

  describe('AC-1: buildBubbleOption returns ECharts scatter config', () => {
    it('should return valid EChartsOption with scatter series', () => {
      const option = buildBubbleOption(sampleData)

      expect(option).toBeDefined()
      expect(option.series).toBeDefined()
      const series = option.series as Array<{ type: string }>
      expect(series[0].type).toBe('scatter')
    })

    it('should return proper chart structure with title, tooltip, grid', () => {
      const option = buildBubbleOption(sampleData)

      expect(option.title).toBeDefined()
      expect(option.tooltip).toBeDefined()
      expect(option.grid).toBeDefined()
      expect(option.visualMap).toBeDefined()
    })
  })

  describe('AC-2: xAxis=policy intensity, yAxis=performance proof', () => {
    it('should have xAxis configured with policy intensity (0-5)', () => {
      const option = buildBubbleOption(sampleData)

      expect(option.xAxis).toBeDefined()
      const xAxis = option.xAxis as { type: string; name: string; min: number; max: number }
      expect(xAxis.type).toBe('value')
      expect(xAxis.name).toBe('政策强度')
      expect(xAxis.min).toBe(0)
      expect(xAxis.max).toBe(5)
    })

    it('should have yAxis configured with performance proof (0-20)', () => {
      const option = buildBubbleOption(sampleData)

      expect(option.yAxis).toBeDefined()
      const yAxis = option.yAxis as { type: string; name: string; min: number; max: number }
      expect(yAxis.type).toBe('value')
      expect(yAxis.name).toBe('业绩兑现')
      expect(yAxis.min).toBe(0)
      expect(yAxis.max).toBe(20)
    })
  })

  describe('AC-3: symbolSize=score mapping', () => {
    it('should have symbolSize as a function', () => {
      const option = buildBubbleOption(sampleData)

      const series = option.series as Array<{ symbolSize?: (val: number[]) => number }>
      expect(series[0].symbolSize).toBeDefined()
      expect(typeof series[0].symbolSize).toBe('function')
    })

    it('should map score=0 to symbolSize=10 (minimum)', () => {
      const option = buildBubbleOption(sampleData)

      const series = option.series as Array<{ symbolSize?: (val: number[]) => number }>
      const size = series[0].symbolSize!([0, 0, 0, 0])
      expect(size).toBe(10)
    })

    it('should map score=18 to larger symbolSize', () => {
      const option = buildBubbleOption(sampleData)

      const series = option.series as Array<{ symbolSize?: (val: number[]) => number }>
      const size = series[0].symbolSize!([4, 15, 3, 18])
      expect(size).toBeGreaterThan(10)
      expect(size).toBeLessThanOrEqual(60)
    })
  })

  describe('AC-4: visualMap color=resonance level', () => {
    it('should have visualMap with piecewise type', () => {
      const option = buildBubbleOption(sampleData)

      expect(option.visualMap).toBeDefined()
      const visualMap = option.visualMap as { type: string; pieces: Array<{ value: number; label: string }> }
      expect(visualMap.type).toBe('piecewise')
    })

    it('should have visualMap pieces for all resonance levels', () => {
      const option = buildBubbleOption(sampleData)

      const visualMap = option.visualMap as { pieces: Array<{ value: number; label: string }> }
      const labels = visualMap.pieces.map(p => p.label)
      expect(labels).toContain('观望')
      expect(labels).toContain('观察')
      expect(labels).toContain('启动')
      expect(labels).toContain('强启动')
    })

    it('should map resonance levels to correct colors', () => {
      const option = buildBubbleOption(sampleData)

      const visualMap = option.visualMap as { pieces: Array<{ value: number; label: string; color: string }> }
      const colorMap: Record<string, string> = {}
      visualMap.pieces.forEach(p => {
        colorMap[p.label] = p.color
      })

      expect(colorMap['强启动']).toBe('#ff4d4f') // red
      expect(colorMap['启动']).toBe('#fa8c16')   // orange
      expect(colorMap['观察']).toBe('#1677ff')   // blue
      expect(colorMap['观望']).toBe('#8c8c8c')   // gray
    })
  })

  describe('AC-5: tooltip shows candidate details', () => {
    it('should have tooltip with item trigger', () => {
      const option = buildBubbleOption(sampleData)

      expect(option.tooltip).toBeDefined()
      const tooltip = option.tooltip as { trigger: string }
      expect(tooltip.trigger).toBe('item')
    })

    it('should have tooltip formatter that returns HTML with candidate info', () => {
      const option = buildBubbleOption(sampleData)

      const tooltip = option.tooltip as { formatter: (params: unknown) => string }
      expect(tooltip.formatter).toBeDefined()
      expect(typeof tooltip.formatter).toBe('function')

      // Simulate tooltip call with mock params
      const mockParams = {
        data: {
          value: [4, 15, 3, 18],
          name: '测试公司A',
          code: '600001',
        },
      }
      const html = tooltip.formatter(mockParams)

      expect(html).toContain('测试公司A')
      expect(html).toContain('600001')
      expect(html).toContain('强启动')
      expect(html).toContain('政策强度')
      expect(html).toContain('业绩兑现')
      expect(html).toContain('综合评分')
    })
  })

  describe('Dark mode support', () => {
    it('should have dark text colors when dark=true', () => {
      const darkOption = buildBubbleOption(sampleData, true)
      const lightOption = buildBubbleOption(sampleData, false)

      const darkTitle = darkOption.title as { textStyle: { color: string } }
      const lightTitle = lightOption.title as { textStyle: { color: string } }

      expect(darkTitle.textStyle.color).toBe('#e0e0e0')
      expect(lightTitle.textStyle.color).toBe('#333')
    })

    it('should have dark background when dark=true', () => {
      const darkOption = buildBubbleOption(sampleData, true)
      const lightOption = buildBubbleOption(sampleData, false)

      expect(darkOption.backgroundColor).toBe('#1f1f1f')
      expect(lightOption.backgroundColor).toBe('#fff')
    })
  })

  describe('Empty data handling', () => {
    it('should handle empty data array', () => {
      const option = buildBubbleOption([])

      expect(option).toBeDefined()
      const series = option.series as Array<{ data: Array<{ value: number[] }> }>
      expect(series[0].data).toHaveLength(0)
    })
  })
})

describe('candidateToBubblePoint', () => {
  it('should convert CandidateCompany to BubbleDataPoint', () => {
    const candidate: CandidateCompany = {
      code: '600001',
      name: '测试公司',
      score: 15,
      trade_signal: '强启动',
      dimension_scores: {
        policy_intensity: 4,
        performance_proof: 12,
      },
      industry: '半导体',
    }

    const point = candidateToBubblePoint(candidate)

    expect(point.code).toBe('600001')
    expect(point.name).toBe('测试公司')
    expect(point.policyIntensity).toBe(4)
    expect(point.performanceProof).toBe(12)
    expect(point.score).toBe(15)
    expect(point.resonanceLevel).toBe('强启动')
    expect(point.resonanceValue).toBe(3)
  })

  it('should default resonance to 观望 when no trade_signal', () => {
    const candidate: CandidateCompany = {
      code: '600002',
      name: '测试公司B',
      score: 5,
    }

    const point = candidateToBubblePoint(candidate)

    expect(point.resonanceLevel).toBe('观望')
    expect(point.resonanceValue).toBe(0)
  })

  it('should set resonance to 观察 when score >= 12 and no signal', () => {
    const candidate: CandidateCompany = {
      code: '600003',
      name: '测试公司C',
      score: 14,
    }

    const point = candidateToBubblePoint(candidate)

    expect(point.resonanceLevel).toBe('观察')
    expect(point.resonanceValue).toBe(1)
  })

  it('should clamp policyIntensity to 0-5 range', () => {
    const candidate1: CandidateCompany = {
      code: '600001',
      dimension_scores: { policy_intensity: 10 },
    }
    const candidate2: CandidateCompany = {
      code: '600002',
      dimension_scores: { policy_intensity: -5 },
    }

    expect(candidateToBubblePoint(candidate1).policyIntensity).toBe(5)
    expect(candidateToBubblePoint(candidate2).policyIntensity).toBe(0)
  })

  it('should clamp performanceProof to 0-20 range', () => {
    const candidate1: CandidateCompany = {
      code: '600001',
      dimension_scores: { performance_proof: 30 },
    }
    const candidate2: CandidateCompany = {
      code: '600002',
      dimension_scores: { performance_proof: -10 },
    }

    expect(candidateToBubblePoint(candidate1).performanceProof).toBe(20)
    expect(candidateToBubblePoint(candidate2).performanceProof).toBe(0)
  })
})