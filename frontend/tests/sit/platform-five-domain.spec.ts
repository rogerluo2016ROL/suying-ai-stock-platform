import { test, expect } from '@playwright/test'

test('runtime page is reachable without live trading', async ({ page }) => {
  await page.goto('/runtime-status')
  await expect(page).toHaveURL(/runtime-status/)
})
