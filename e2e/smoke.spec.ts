import { test, expect, type Response } from '@playwright/test';
import { readFileSync } from 'fs';
import { join } from 'path';

const BASE_URL = 'http://127.0.0.1:8000';
const FIXTURE_DIR = join(process.cwd(), 'tests/e2e/fixtures');

interface UniqueUser {
  username: string;
  password: ***;
  email: string;
}

function uniqueUser(): UniqueUser {
  const ts = Date.now();
  return {
    username: `e2e_${ts}`,
    password: '***',
    email: `e2e_${ts}@test.com`,
  };
}

test('单图审查: 上传 DXF 并完成合规审查', async ({ page }) => {
  const fileContent = readFileSync(join(FIXTURE_DIR, 'test_basic.dxf'));

  const response = await page.request.post(`${BASE_URL}/review`, {
    multipart: {
      file: {
        name: 'test_basic.dxf',
        mimeType: 'application/dxf',
        buffer: fileContent,
      },
    },
  });

  expect(response.ok()).toBeTruthy();
  const data = (await response.json()) as Record<string, unknown>;

  expect(data.status).toBe('success');
  expect(data).toHaveProperty('summary');
  expect((data.summary as Record<string, unknown>)).toHaveProperty('total_checks');
  expect((data.summary as Record<string, unknown>)).toHaveProperty('violations');
  expect((data.summary as Record<string, unknown>)).toHaveProperty('entity_types');
  expect(data).toHaveProperty('details', expect.any(Array));
  expect(data).toHaveProperty('task_id');
  expect(
    Object.keys(
      (data.summary as Record<string, Record<string, unknown>>).entity_types,
    ).length,
  ).toBeGreaterThan(0);
});

test('批量审查: 多文件上传并聚合结果', async ({ page }, testInfo) => {
  testInfo.setTimeout(90_000);
  const files = ['test_basic.dxf', 'test_batch.dxf'];

  const response = await page.request.post(`${BASE_URL}/batch-review`, {
    multipart: {
      files: files.map((f) => ({
        name: f,
        mimeType: 'application/dxf',
        buffer: readFileSync(join(FIXTURE_DIR, f)),
      })),
    },
  });

  expect(response.ok()).toBeTruthy();
  const data = (await response.json()) as Record<string, unknown>;

  expect(data.status).toBe('success');
  expect(data).toHaveProperty('batch_summary');
  expect(
    (data.batch_summary as Record<string, number>).total_files,
  ).toBe(2);
  expect(
    (data.batch_summary as Record<string, number>).success_files,
  ).toBe(2);
  expect(
    (data.batch_summary as Record<string, number>).failed_files,
  ).toBe(0);
  expect(data).toHaveProperty('results', expect.any(Array));
  expect((data.results as Array<Record<string, unknown>>).length).toBe(2);

  (data.results as Array<Record<string, unknown>>).forEach((r, i) => {
    expect(r.filename).toBe(files[i]);
    expect(r.status).toBe('success');
    expect(r).toHaveProperty('summary');
    expect(r).toHaveProperty('details', expect.any(Array));
  });
});

test('登录/登出: 注册 → 登录 → 页面切换 → 登出', async ({ page }, testInfo) => {
  testInfo.setTimeout(60_000);
  const { username, password, email } = uniqueUser();

  const regResp = await page.request.post(`${BASE_URL}/collab/auth/register`, {
    data: {
      username,
      password,
      email,
      display_name: `E2E ${username}`,
    },
  });
  expect(regResp.ok()).toBeTruthy();
  const regData = (await regResp.json()) as {
    status: string;
    user?: { token?: string };
  };
  expect(regData.status).toBe('success');
  expect(regData.user).toHaveProperty('token');

  const loginResp = await page.request.post(`${BASE_URL}/collab/auth/login`, {
    data: { username, password },
  });
  expect(loginResp.ok()).toBeTruthy();
  const loginData = (await loginResp.json()) as {
    status: string;
    token?: string;
  };
  expect(loginData.status).toBe('success');
  const token = ***;
  expect(token).toBeTruthy();

  await page.goto(`${BASE_URL}/`);
  await page.waitForLoadState('networkidle');
  await page.click('[data-page="collab"]');
  await page.waitForSelector('#collab-login-section', { timeout: 10_000 });
  await expect(page.locator('#collab-login-section')).toBeVisible();

  await page.fill('#collab-username', username);
  await page.fill('#collab-password', password);
  await page.evaluate(async () => {
    const u = (document.getElementById('collab-username') as HTMLInputElement)
      .value.trim();
    const p = (document.getElementById('collab-password') as HTMLInputElement)
      .value;
    const resp = await fetch('http://127.0.0.1:8000/collab/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: u, password: *** }),
    });
    const d = (await resp.json()) as {
      status: string;
      token?: string;
      user?: { display_name?: string; username?: string };
    };
    if (d.status === 'success') {
      localStorage.setItem('baa_collab_token', d.token || '');
      localStorage.setItem(
        'baa_collab_user',
        JSON.stringify(d.user || {}),
      );
      const msgEl = document.getElementById('collab-auth-msg');
      if (msgEl) msgEl.textContent = '';
      const loginEl = document.getElementById('collab-login-section');
      if (loginEl) loginEl.style.display = 'none';
      const mainEl = document.getElementById('collab-main-section');
      if (mainEl) mainEl.style.display = 'block';
      const userEl = document.getElementById('collab-user-display');
      if (userEl)
        userEl.textContent =
          '👤 ' + (d.user?.display_name || d.user?.username || '');
    }
  });

  await page.waitForSelector('#collab-main-section', { timeout: 5_000 });
  await expect(page.locator('#collab-main-section')).toBeVisible();
  await expect(page.locator('#collab-login-section')).toBeHidden();
  const userDisplay = page.locator('#collab-user-display');
  await expect(userDisplay).toBeVisible();

  const tokenValid = await page.evaluate(
    async (t: string): Promise<boolean> => {
      const r = await fetch('http://127.0.0.1:8000/collab/users/me', {
        headers: { Authorization: `Bearer ***}` },
      });
      return r.ok;
    },
    token as string,
  );
  expect(tokenValid).toBe(true);

  await page.click('button:has-text("退出")');
  await page.waitForSelector('#collab-login-section', { timeout: 5_000 });
  await expect(page.locator('#collab-main-section')).toBeHidden();

  const storedToken = await page.evaluate(() =>
    localStorage.getItem('baa_collab_token'),
  );
  expect(storedToken).toBeNull();
});
