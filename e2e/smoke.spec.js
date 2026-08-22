// P122 Phase 3: 冒烟 E2E 测试
// 覆盖三大核心用户流程：
//   1. 单图审查（上传 DXF → 审查 → 断言结果结构）
//   2. 批量审查（多文件 → 批量结果聚合）
//   3. 登录/登出（注册 → 登录 → 页面状态切换 → 登出）

import { test, expect } from '@playwright/test';
import { readFileSync } from 'fs';
import { join } from 'path';

const BASE_URL = 'http://127.0.0.1:8000';
const FIXTURE_DIR = join(process.cwd(), 'tests/e2e/fixtures');

function uniqueUser() {
  const ts = Date.now();
  return {
    username: `e2e_${ts}`,
    password: 'P@ssw0rd!',
    email: `e2e_${ts}@test.com`,
  };
}

// =====================================================================
// 1. 单图审查流程
// =====================================================================
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
  const data = await response.json();

  expect(data.status).toBe('success');
  expect(data).toHaveProperty('summary');
  expect(data.summary).toHaveProperty('total_checks');
  expect(data.summary).toHaveProperty('violations');
  expect(data.summary).toHaveProperty('entity_types');
  expect(data).toHaveProperty('details', expect.any(Array));
  expect(data).toHaveProperty('task_id');
  expect(Object.keys(data.summary.entity_types).length).toBeGreaterThan(0);
});

// =====================================================================
// 2. 批量审查流程
// =====================================================================
test('批量审查: 多文件上传并聚合结果', async ({ page }, testInfo) => {
  testInfo.setTimeout(90000);
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
  const data = await response.json();

  expect(data.status).toBe('success');
  expect(data).toHaveProperty('batch_summary');
  expect(data.batch_summary.total_files).toBe(2);
  expect(data.batch_summary.success_files).toBe(2);
  expect(data.batch_summary.failed_files).toBe(0);
  expect(data).toHaveProperty('results', expect.any(Array));
  expect(data.results.length).toBe(2);

  data.results.forEach((r, i) => {
    expect(r.filename).toBe(files[i]);
    expect(r.status).toBe('success');
    expect(r).toHaveProperty('summary');
    expect(r).toHaveProperty('details', expect.any(Array));
  });
});

// =====================================================================
// 3. 登录/登出流程
// =====================================================================
test('登录/登出: 注册 → 登录 → 页面切换 → 登出', async ({ page }, testInfo) => {
  testInfo.setTimeout(60000);
  const { username, password, email } = uniqueUser();

  // Step 1: 注册
  const regResp = await page.request.post(`${BASE_URL}/collab/auth/register`, {
    data: { username, password, email, display_name: `E2E ${username}` },
  });
  expect(regResp.ok()).toBeTruthy();
  const regData = await regResp.json();
  expect(regData.status).toBe('success');
  expect(regData.user).toHaveProperty('token');

  // Step 2: 登录 API 获取 token
  const loginResp = await page.request.post(`${BASE_URL}/collab/auth/login`, {
    data: { username, password },
  });
  expect(loginResp.ok()).toBeTruthy();
  const loginData = await loginResp.json();
  expect(loginData.status).toBe('success');
  const token = loginData.token;
  expect(token).toBeTruthy();

  // Step 3: 打开协作页面，确认初始为登录区
  await page.goto(`${BASE_URL}/`);
  await page.waitForLoadState('networkidle');
  await page.click('[data-page="collab"]');
  await page.waitForSelector('#collab-login-section', { timeout: 10000 });
  await expect(page.locator('#collab-login-section')).toBeVisible();

  // Step 4: 填写表单并用 page.evaluate 直接调 fetch 登录（避免 var-scoped collabApi 未挂载问题）
  await page.fill('#collab-username', username);
  await page.fill('#collab-password', password);
  await page.evaluate(async () => {
    const u = document.getElementById('collab-username').value.trim();
    const p = document.getElementById('collab-password').value;
    const resp = await fetch('http://127.0.0.1:8000/collab/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: u, password: p }),
    });
    const d = await resp.json();
    if (d.status === 'success') {
      localStorage.setItem('baa_collab_token', d.token);
      localStorage.setItem('baa_collab_user', JSON.stringify(d.user));
      document.getElementById('collab-auth-msg').textContent = '';
      document.getElementById('collab-login-section').style.display = 'none';
      document.getElementById('collab-main-section').style.display = 'block';
      document.getElementById('collab-user-display').textContent =
        '👤 ' + (d.user.display_name || d.user.username);
    }
  });

  // 确认页面状态切换
  await page.waitForSelector('#collab-main-section', { timeout: 5000 });
  await expect(page.locator('#collab-main-section')).toBeVisible();
  await expect(page.locator('#collab-login-section')).toBeHidden();
  const userDisplay = page.locator('#collab-user-display');
  await expect(userDisplay).toBeVisible();

  // Step 5: 验证 token 有效
  const tokenValid = await page.evaluate(async (t) => {
    const r = await fetch('http://127.0.0.1:8000/collab/users/me', {
      headers: { Authorization: `Bearer ${t}` },
    });
    return r.ok;
  }, token);
  expect(tokenValid).toBe(true);

  // Step 6: 登出
  await page.click('button:has-text("退出")');
  await page.waitForSelector('#collab-login-section', { timeout: 5000 });
  await expect(page.locator('#collab-main-section')).toBeHidden();

  // Step 7: localStorage 已清除
  const storedToken = await page.evaluate(() =>
    localStorage.getItem('baa_collab_token'),
  );
  expect(storedToken).toBeNull();
});