import { describe, expect, it } from 'vitest'
import { buildTradeUrlForPick } from '../pages/Strategy'

describe('Strategy lineage handoff', () => {
  it('builds trade URL with plan and candidate lineage', () => {
    const url = buildTradeUrlForPick('PLAN-1', {
      code: '300750',
      candidate_id: 'CAND-leader_auction-300750',
      source_mode: 'leader_auction',
      entry_price: 218.5,
    })

    expect(url).toBe(
      '/trade?code=300750&price=218.5&plan_id=PLAN-1&candidate_id=CAND-leader_auction-300750&decision_context_id=CTX-PLAN-1-leader_auction-300750',
    )
  })
})
