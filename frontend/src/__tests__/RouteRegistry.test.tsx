import { describe, expect, it } from 'vitest'
import { buildMenuItems, buildProtectedRoutes, routeRegistry } from '../app/routeRegistry'

describe('route registry', () => {
  it('derives menu and protected routes from the same registry', () => {
    const definition = routeRegistry.find(item => item.path === '/screener')!
    expect(buildMenuItems('admin')).toContainEqual(expect.objectContaining({ key: definition.path }))
    expect(buildProtectedRoutes()).toContainEqual(expect.objectContaining({ path: definition.path }))
    expect(definition.permission).toBe('screener')
  })
})
