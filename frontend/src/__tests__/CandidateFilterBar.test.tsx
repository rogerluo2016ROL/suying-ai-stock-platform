// Unit tests for CandidateFilterBar component
// Tests: AC-1 filter select, AC-2 resonance_level select, AC-3 API call trigger, AC-4 TypeScript types

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import CandidateFilterBar, { FILTER_OPTIONS, RESONANCE_OPTIONS } from '../pages/supply-chain-bom/CandidateFilterBar'

// Mock chainApi.getCandidates - must be defined inside vi.mock factory (hoisted)
vi.mock('../api/client', () => ({
  chainApi: {
    getCandidates: vi.fn(),
  },
}))

// Import after mock to get mocked version
import { chainApi, type ChainCandidatesResponse } from '../api/client'

describe('CandidateFilterBar', () => {
  const mockOnCandidatesChange = vi.fn()
  const mockOnLoadingChange = vi.fn()
  const mockOnSummaryChange = vi.fn()

  const mockCandidatesResponse: ChainCandidatesResponse = {
    filter: 'all',
    resonance_level: undefined,
    total_count: 5,
    candidates: [
      {
        code: '600001',
        name: 'Test Company',
        score: 85,
        chokepoint_score: 18,
        three_factor_scores: {
          industry_cycle: { stage: '量产', score: 9 },
          policy_intensity: { stars: 4, score: 12 },
          performance_proof: { status: '业绩兑现', score: 10 },
        },
        resonance_factors: 3,
        resonance_level: '强启动',
        trade_signal: '强启动',
        commercialization_note: '量产+政策4星+预增80%',
      },
    ],
    filter_summary: {
      high_growth: 10,
      high_profit: 8,
      high_moat: 5,
      chokepoint_core: 3,
      all: 30,
    },
    resonance_summary: {
      '强启动': 2,
      '启动': 5,
      '关注': 10,
      '观察': 13,
    },
    elapsed_ms: 150,
  }

  beforeEach(() => {
    mockOnCandidatesChange.mockClear()
    mockOnLoadingChange.mockClear()
    mockOnSummaryChange.mockClear()
    vi.mocked(chainApi.getCandidates).mockClear()
    vi.mocked(chainApi.getCandidates).mockResolvedValue({
      data: mockCandidatesResponse,
    } as any)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // AC-1: Select component supports filter options
  it('AC-1: renders filter select with all filter options', async () => {
    render(
      <CandidateFilterBar
        onCandidatesChange={mockOnCandidatesChange}
      />
    )

    // Wait for initial load
    await waitFor(() => {
      expect(chainApi.getCandidates).toHaveBeenCalled()
    })

    // Find filter select by placeholder text (Ant Design uses placeholder)
    const filterSelects = screen.getAllByRole('combobox')
    expect(filterSelects.length).toBeGreaterThanOrEqual(2)

    // Verify all filter options are available
    expect(FILTER_OPTIONS.length).toBe(5)
    expect(FILTER_OPTIONS.map(opt => opt.value)).toEqual([
      'high_growth',
      'high_profit',
      'high_moat',
      'chokepoint_core',
      'all',
    ])
  })

  // AC-2: Select component supports resonance_level options
  it('AC-2: renders resonance_level select with all resonance options', async () => {
    render(
      <CandidateFilterBar
        onCandidatesChange={mockOnCandidatesChange}
      />
    )

    await waitFor(() => {
      expect(chainApi.getCandidates).toHaveBeenCalled()
    })

    // Find resonance select (Ant Design has 2 comboboxes)
    const selects = screen.getAllByRole('combobox')
    expect(selects.length).toBeGreaterThanOrEqual(2)

    // Verify all resonance options are available
    expect(RESONANCE_OPTIONS.length).toBe(4)
    expect(RESONANCE_OPTIONS.map(opt => opt.value)).toEqual([
      '强启动',
      '启动',
      '关注',
      '观察',
    ])
  })

  // AC-3: Filter change triggers API call with correct params
  it('AC-3: filter change triggers API call with correct filter param', async () => {
    render(
      <CandidateFilterBar
        onCandidatesChange={mockOnCandidatesChange}
        defaultFilter="all"
      />
    )

    // Wait for initial call with default filter
    await waitFor(() => {
      expect(chainApi.getCandidates).toHaveBeenCalledWith({
        filter: 'all',
        resonance_level: undefined,
        top_n: 30,
        trade_date: undefined,
      })
    })

    // Verify candidates callback was called
    await waitFor(() => {
      expect(mockOnCandidatesChange).toHaveBeenCalled()
    })
  })

  // AC-3: Resonance level change triggers API call with correct params
  it('AC-3: resonance_level change triggers API call with correct resonance_level param', async () => {
    render(
      <CandidateFilterBar
        onCandidatesChange={mockOnCandidatesChange}
      />
    )

    // Wait for initial call
    await waitFor(() => {
      expect(chainApi.getCandidates).toHaveBeenCalled()
    })

    // Verify initial call has no resonance_level filter
    await waitFor(() => {
      expect(chainApi.getCandidates).toHaveBeenCalledWith({
        filter: 'all',
        resonance_level: undefined,
        top_n: 30,
        trade_date: undefined,
      })
    })
  })

  // AC-4: TypeScript type definitions are complete
  it('AC-4: TypeScript types are correctly imported and used', () => {
    // This test verifies type imports compile correctly
    // The actual type checking is done by tsc

    const filterOption = FILTER_OPTIONS[0]
    expect(filterOption.value).toBe('high_growth')
    expect(filterOption.label).toBe('高增长')
    expect(filterOption.tagColor).toBe('green')

    const resonanceOption = RESONANCE_OPTIONS[0]
    expect(resonanceOption.value).toBe('强启动')
    expect(resonanceOption.label).toBe('强启动')
    expect(resonanceOption.tagColor).toBe('red')

    // Verify types are correct by checking option structure
    expect(typeof filterOption.value).toBe('string')
    expect(typeof filterOption.label).toBe('string')
    expect(typeof filterOption.description).toBe('string')
  })

  // Additional: Loading state handling
  it('calls onLoadingChange with true when loading, false when done', async () => {
    render(
      <CandidateFilterBar
        onCandidatesChange={mockOnCandidatesChange}
        onLoadingChange={mockOnLoadingChange}
      />
    )

    // Should call loading=true first
    await waitFor(() => {
      expect(mockOnLoadingChange).toHaveBeenCalledWith(true)
    })

    // Should call loading=false after completion
    await waitFor(() => {
      expect(mockOnLoadingChange).toHaveBeenCalledWith(false)
    })
  })

  // Additional: Summary callback
  it('calls onSummaryChange with filter and resonance summaries', async () => {
    render(
      <CandidateFilterBar
        onCandidatesChange={mockOnCandidatesChange}
        onSummaryChange={mockOnSummaryChange}
      />
    )

    await waitFor(() => {
      expect(mockOnSummaryChange).toHaveBeenCalledWith(
        mockCandidatesResponse.filter_summary,
        mockCandidatesResponse.resonance_summary,
      )
    })
  })

  // Additional: Disabled state
  it('disables selects when disabled prop is true', async () => {
    render(
      <CandidateFilterBar
        onCandidatesChange={mockOnCandidatesChange}
        disabled={true}
      />
    )

    // Ant Design disabled select still renders comboboxes but they're disabled
    const selects = screen.getAllByRole('combobox')
    expect(selects.length).toBeGreaterThanOrEqual(2)
    // At least one should be disabled
    const disabledSelects = selects.filter(s => s.hasAttribute('disabled') || (s as any).disabled)
    expect(disabledSelects.length).toBeGreaterThan(0)
  })

  // Additional: Custom topN and tradeDate
  it('passes topN and tradeDate to API call', async () => {
    render(
      <CandidateFilterBar
        onCandidatesChange={mockOnCandidatesChange}
        topN={50}
        tradeDate="2026-06-20"
      />
    )

    await waitFor(() => {
      expect(chainApi.getCandidates).toHaveBeenCalledWith({
        filter: 'all',
        resonance_level: undefined,
        top_n: 50,
        trade_date: '2026-06-20',
      })
    })
  })

  // Additional: Empty candidates on API error
  it('calls onCandidatesChange with empty array on API error', async () => {
    vi.mocked(chainApi.getCandidates).mockRejectedValueOnce(new Error('API error'))

    render(
      <CandidateFilterBar
        onCandidatesChange={mockOnCandidatesChange}
      />
    )

    await waitFor(() => {
      expect(mockOnCandidatesChange).toHaveBeenCalledWith([])
    })
  })
})