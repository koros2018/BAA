import { test, expect, type Page } from '@playwright/test';

const VIEWPORTS = [
  { name: 'mobile', width: 375, height: 667 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'laptop', width: 1280, height: 800 },
  { name: 'desktop', width: 1920, height: 1080 },
];

const CORE_PAGES = [
  { hash: '#home', id: 'page-home' },
  { hash: '#drawings', id: 'page-drawings' },
  { hash: '#history', id: 'page-history' },
  { hash: '#collab', id: 'page-collab' },
];

async function noHorizontalScroll(page: Page) {
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  const innerWidth = await page.evaluate(() => window.innerWidth);
  expect(scrollWidth).toBeLessThanOrEqual(innerWidth + 1);
}

for (const vp of VIEWPORTS) {
  for (const pg of CORE_PAGES) {
    test(`${vp.name} (${vp.width}px) - ${pg.id} no horizontal scroll`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto('/');
      await page.waitForLoadState('domcontentloaded');
      await page.evaluate((h) => { window.location.hash = h; }, pg.hash);
      await page.waitForTimeout(500);
      await noHorizontalScroll(page);
      const el = page.locator(`#${pg.id}`);
      await expect(el).toBeVisible();
    });
  }
}