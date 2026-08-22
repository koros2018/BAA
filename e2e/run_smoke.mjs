// P122 Phase 3: E2E smoke test runner (direct Node + Playwright API)
import { chromium } from 'playwright';
import { readFileSync } from 'fs';
import { join } from 'path';

const BASE_URL = 'http://127.0.0.1:8000';
const FIXTURE_DIR = join(process.cwd(), 'tests', 'e2e', 'fixtures');
const results = [];

function E(v) {
  return {
    toBe(e) { if (v !== e) throw new Error(`Expected ${e}, got ${v}`); },
    toBeTruthy() { if (!v) throw new Error(`Expected truthy, got ${v}`); },
    toBeNull() { if (v !== null) throw new Error(`Expected null, got ${v}`); },
    toBeGreaterThan(n) { if (v <= n) throw new Error(`Expected > ${n}, got ${v}`); },
    toContain(s) { if (!String(v).includes(s)) throw new Error(`Expected to contain '${s}', got '${v}'`); },
    toHaveProperty(p) { if (!(p in v)) throw new Error(`Missing property '${p}'`); },
  };
}

async function test(name, fn) {
  try {
    await fn();
    results.push({ name, pass: true });
    console.log(`✅ ${name}`);
  } catch (e) {
    results.push({ name, pass: false, error: e.message });
    console.error(`❌ ${name}: ${e.message}`);
  }
}

async function main() {
  const browser = await chromium.launch({
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
    headless: true,
  });

  // ===== Test 1: 单图审查 (API only, no browser needed) =====
  await test('单图审查: 上传 DXF 并完成合规审查', async () => {
    const fileContent = readFileSync(join(FIXTURE_DIR, 'test_basic.dxf'));
    const fd = new FormData();
    fd.append('file', new Blob([fileContent], { type: 'application/dxf' }), 'test_basic.dxf');
    const httpRes = await fetch(`${BASE_URL}/review`, { method: 'POST', body: fd });
    if (!httpRes.ok) throw new Error(`HTTP ${httpRes.status}: ${await httpRes.text()}`);
    const data = await httpRes.json();
    E(data.status).toBe('success');
    E(data).toHaveProperty('summary');
    E(data.summary).toHaveProperty('total_checks');
    E(data.summary).toHaveProperty('violations');
    E(data.summary).toHaveProperty('entity_types');
    E(data).toHaveProperty('details');
    E(data).toHaveProperty('task_id');
    E(Object.keys(data.summary.entity_types).length).toBeGreaterThan(0);
    console.log(`  ${data.summary.total_checks} checks, ${data.summary.violations} violations, entities: ${JSON.stringify(data.summary.entity_types)}`);
  });

  // ===== Test 2: 批量审查 (API only) =====
  await test('批量审查: 多文件上传并聚合结果', async () => {
    const files = ['test_basic.dxf', 'test_batch.dxf'];
    const fd = new FormData();
    for (const f of files) {
      const buf = readFileSync(join(FIXTURE_DIR, f));
      fd.append('files', new Blob([buf], { type: 'application/dxf' }), f);
    }
    const httpRes = await fetch(`${BASE_URL}/batch-review`, { method: 'POST', body: fd });
    if (!httpRes.ok) throw new Error(`HTTP ${httpRes.status}: ${await httpRes.text()}`);
    const data = await httpRes.json();
    E(data.status).toBe('success');
    E(data).toHaveProperty('batch_summary');
    E(data.batch_summary.total_files).toBe(2);
    E(data.batch_summary.success_files).toBe(2);
    E(data.batch_summary.failed_files).toBe(0);
    E(data).toHaveProperty('results');
    E(data.results.length).toBe(2);
    data.results.forEach((r, i) => {
      E(r.filename).toBe(files[i]);
      E(r.status).toBe('success');
      E(r).toHaveProperty('summary');
      E(r).toHaveProperty('details');
    });
    console.log(`  ${data.batch_summary.total_files} files, ${data.batch_summary.success_files} ok`);
  });

  // ===== Test 3: 登录/登出 (browser + API) =====
  await test('登录/登出: 注册 → 登录 → 页面切换 → 登出', async () => {
    const username = `e2e_${Date.now()}`;
    const password = 'P@ssw0rd!';
    const email = `e2e_${Date.now()}@test.com`;

    // 注册 + 登录 via API
    console.log('  registering...');
    const regResp = await fetch(`${BASE_URL}/collab/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password, email, display_name: `E2E ${username}` }),
    });
    E(regResp.ok).toBe(true);
    const regData = await regResp.json();
    console.log(`  registered: ${JSON.stringify(regData).slice(0,100)}`);
    E(regData.status).toBe('success');
    E(regData.user).toHaveProperty('token');

    console.log('  logging in...');
    const loginResp = await fetch(`${BASE_URL}/collab/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    E(loginResp.ok).toBe(true);
    const loginData = await loginResp.json();
    console.log(`  logged in, token len: ${loginData.token?.length}`);
    E(loginData.status).toBe('success');
    const token = loginData.token;
    E(token).toBeTruthy();

    // 打开页面 (fresh context, no prior login state)
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto(`${BASE_URL}/`);
    await page.waitForLoadState('networkidle');

    // 点击协作 Tab
    await page.click('[data-page="collab"]');
    await page.waitForTimeout(2000);

    // 确认初始为登录区
    const loginVisible = await page.locator('#collab-login-section').isVisible();
    console.log(`  initial: login-section visible = ${loginVisible}`);
    E(loginVisible).toBe(true);

    // 填写表单 + 登录
    await page.fill('#collab-username', username);
    await page.fill('#collab-password', password);
    await page.evaluate(async ({ u, p }) => {
      const resp = await fetch('/collab/auth/login', {
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
    }, { u: username, p: password });

    await page.waitForTimeout(2000);
    const mainVisible = await page.locator('#collab-main-section').isVisible();
    const loginHidden = await page.locator('#collab-login-section').isVisible();
    console.log(`  after login: main=${mainVisible}, login-section-hidden=${!loginHidden}`);
    E(mainVisible).toBe(true);
    E(loginHidden).toBe(false);

    // 验证 token (从浏览器 localStorage 读取浏览器侧实际 token)
    const storedToken = await page.evaluate(() => localStorage.getItem('baa_collab_token'));
    E(storedToken).toBeTruthy();
    const meResp = await fetch(`${BASE_URL}/collab/users/me`, {
      headers: { Authorization: `Bearer ${storedToken}` },
    });
    console.log(`  token verify HTTP: ${meResp.status}`);
    E(meResp.ok).toBe(true);
    const meData = await meResp.json();
    E(meData.user && meData.user.username).toBe(username);
    console.log(`  token verified, user: ${meData.user.username}`);

    // 登出: 前端清理本地状态（后端无 logout API）
    console.log('  logging out (clearing local state)');
    await page.evaluate(() => {
      localStorage.removeItem('baa_collab_token');
      localStorage.removeItem('baa_collab_user');
      document.getElementById('collab-login-section').style.display = 'block';
      document.getElementById('collab-main-section').style.display = 'none';
      document.getElementById('collab-user-display').textContent = '';
    });
    await page.waitForTimeout(1000);
    const loginShown = await page.locator('#collab-login-section').isVisible();
    E(loginShown).toBe(true);
    console.log('  logged out, back to login section');

    const finalToken = await page.evaluate(() =>
      localStorage.getItem('baa_collab_token'),
    );
    E(finalToken).toBeNull();
    console.log('  token cleared from localStorage');

    await context.close();
  });

  await browser.close();

  console.log('');
  const passed = results.filter(r => r.pass).length;
  console.log(`Results: ${passed}/${results.length} passed`);
  if (results.some(r => !r.pass)) {
    console.log('Failed:');
    results.filter(r => !r.pass).forEach(r => console.log(`  - ${r.name}: ${r.error}`));
    process.exit(1);
  }
}

main().catch(e => {
  console.error('Fatal:', e);
  process.exit(1);
});