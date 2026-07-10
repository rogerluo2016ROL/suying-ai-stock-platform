import { describe, expect, it } from 'vitest'
import { buildMenuItems, buildProtectedRoutes, routeRegistry } from '../app/routeRegistry'

describe('route registry', () => {
  it('derives menu and protected routes from the same registry', () => {
    const definition = routeRegistry.find(item => item.path === '/screener')!
    expect(buildMenuItems('admin')).toContainEqual(expect.objectContaining({ key: definition.path }))
    expect(buildProtectedRoutes()).toContainEqual(expect.objectContaining({ path: definition.path }))
    expect(definition.permission).toBe('screener')
  })

  it('expands every alias once with the same permission contract', () => {
    const routes = buildProtectedRoutes()
    const expectedCount = routeRegistry.reduce((count, route) => count + 1 + (route.aliases?.length || 0), 0)
    expect(routes).toHaveLength(expectedCount)
    expect(new Set(routes.map(route => route.path)).size).toBe(routes.length)
    const alias = routes.find(route => route.path === '/trade/positions')!
    expect(alias.permission).toBe('trade')
  })

  it('keeps every visible route reachable from the admin menu', () => {
    const menuKeys = new Set(buildMenuItems('admin').map(item => item.key))
    for (const route of routeRegistry.filter(item => item.navVisible)) {
      expect(menuKeys.has(route.path)).toBe(true)
    }
  })
})
