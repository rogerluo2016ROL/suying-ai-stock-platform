import { describe, expect, it } from 'vitest'

import { resolveProxyTargets } from '../../proxyTargets'

describe('resolveProxyTargets', () => {
  it('uses the suying-uat published ports as defaults so the dev entry can log in', () => {
    const targets = resolveProxyTargets({})

    expect(targets.auth).toBe('http://127.0.0.1:8900')
    expect(targets.screener).toBe('http://127.0.0.1:8901')
    expect(targets.trade).toBe('http://127.0.0.1:8906')
    expect(targets.diagnosis).toBe('http://127.0.0.1:8909')
  })

  it('honors UAT service targets from the environment', () => {
    const targets = resolveProxyTargets({
      VITE_AUTH_SERVICE_URL: 'http://127.0.0.1:8900',
      VITE_SCREENER_SERVICE_URL: 'http://127.0.0.1:8901',
    })

    expect(targets.auth).toBe('http://127.0.0.1:8900')
    expect(targets.screener).toBe('http://127.0.0.1:8901')
  })
})
