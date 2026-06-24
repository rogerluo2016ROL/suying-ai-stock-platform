import { describe, expect, it } from 'vitest'

import { resolveProxyTargets } from '../../proxyTargets'

describe('resolveProxyTargets', () => {
  it('keeps canonical local service ports as defaults', () => {
    const targets = resolveProxyTargets({})

    expect(targets.auth).toBe('http://localhost:9001')
    expect(targets.screener).toBe('http://localhost:8001')
  })

  it('honors UAT service targets from the environment', () => {
    const targets = resolveProxyTargets({
      VITE_AUTH_SERVICE_URL: 'http://127.0.0.1:19001',
      VITE_SCREENER_SERVICE_URL: 'http://127.0.0.1:18001',
    })

    expect(targets.auth).toBe('http://127.0.0.1:19001')
    expect(targets.screener).toBe('http://127.0.0.1:18001')
  })
})
