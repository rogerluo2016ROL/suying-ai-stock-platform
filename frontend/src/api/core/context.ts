import type { PlatformSession } from '../../types/platform'

let tokenProvider: (() => string | null) | null = null
let sessionProvider: (() => PlatformSession | null) | null = null

export const apiContext = {
  token: () => tokenProvider?.() || null,
  session: () => sessionProvider?.() || null,
}

export function configureApiContext(options: {
  getToken?: () => string | null
  getSession?: () => PlatformSession | null
}) {
  if ('getToken' in options) tokenProvider = options.getToken || null
  if ('getSession' in options) sessionProvider = options.getSession || null
}

export function clearApiContext() {
  tokenProvider = null
  sessionProvider = null
}
