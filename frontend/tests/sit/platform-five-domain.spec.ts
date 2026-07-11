import { test, expect } from '@playwright/test'

test('runtime page is reachable without live trading', async ({ page }) => {
  const baseURL = process.env.UAT_BASE_URL ?? 'http://127.0.0.1:28981'
  const response = await page.goto(`${baseURL}/runtime-status`)
  expect(response?.ok()).toBe(true)
  await expect(page).toHaveURL(/runtime-status/)
  await expect(page.locator('body')).not.toContainText('mock')
})
