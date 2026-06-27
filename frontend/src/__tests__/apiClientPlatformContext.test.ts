import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import api, { clearPlatformContext, injectPlatformContext } from '../api/client'
import type { PlatformSession } from '../types/platform'

const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  server.resetHandlers()
  clearPlatformContext()
})
afterAll(() => server.close())

const session: PlatformSession = {
  tenantId: 'tenant-alpha',
  tenantName: 'Alpha 机构',
  ownerUserId: '12',
  accountId: 'paper-001',
  visibility: 'private',
  dataScope: 'account',
  roleView: 'trader',
  userName: '毕师傅',
  tradeMode: 'paper',
  brokerAdapter: 'paper',
  cloudReady: true,
}

describe('api platform context headers', () => {
  it('attaches tenant and account boundaries to API requests', async () => {
    let tenantId: string | null = null
    let accountId: string | null = null
    let dataScope: string | null = null

    server.use(
      http.get('/api/v1/platform-context-test', ({ request }) => {
        tenantId = request.headers.get('X-Tenant-Id')
        accountId = request.headers.get('X-Trade-Account-Id')
        dataScope = request.headers.get('X-Data-Scope')
        return HttpResponse.json({ ok: true })
      }),
    )

    injectPlatformContext(() => session)
    await api.get('/platform-context-test')

    expect(tenantId).toBe('tenant-alpha')
    expect(accountId).toBe('paper-001')
    expect(dataScope).toBe('account')
  })
})
