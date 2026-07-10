import { describe, expect, it } from 'vitest'
import { resolveRoute } from '../routes/registry'

describe('route registry', () => {
  it('derives title, menu and permission from one definition', () => {
    expect(resolveRoute('/trade/risk-verdicts')).toMatchObject({
      title: '风控闸门', menuKey: '/trade', permission: 'trade',
    })
  })
})
