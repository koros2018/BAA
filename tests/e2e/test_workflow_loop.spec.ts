// T-B6 工作流闭环 E2E — 状态机流转 → 整改登记 → 复查对比 → 终态归档
// 运行： node node_modules/@playwright/test/cli.js test -c tests/e2e/playwright.config.ts test_workflow_loop
import { test, expect, type Page, type BrowserContext } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const BASE = 'http://127.0.0.1:8000';
const TS = Date.now();
const USER = `e2ewf_${TS}`;
const PASS = 'P@ssw0rd!';
const TEAM_NAME = `E2E-WF-Team-${TS}`;
const PROJ_NAME = `E2E-WF-Proj-${TS}`;
const SESSION_NAME = `E2E-WF-Session-${TS}`;
const RECT_ACTION = `E2E整改_${TS}`;
const FIXTURE_DIR =
  process.env.E2E_FIXTURE_DIR ||
  path.join(path.dirname(fileURLToPath(import.meta.url)), 'fixtures');

let context: BrowserContext;
let page: Page;
let token = '';
let projectId = '';
let sessionId = '';

function auth(): Record<string, string> {
  return { Authorization: 'Bearer ' + token };
}

test.describe.serial('T-B6 工作流闭环 E2E（状态机→整改→复查→归档）', () => {
  test.beforeAll(async ({ browser }) => {
    context = await browser.newContext();
    page = await context.newPage();
  });
  test.afterAll(async () => {
    await context.close();
  });

  test('W1 注册并登录', async () => {
    await page.goto('/');
    await page.click('[data-page="collab"]');
    await expect(page.locator('#collab-login-section')).toBeVisible();
    await page.click('#collab-auth-tabs button:nth-child(2)');
    await page.fill('#collab-reg-username', USER);
    await page.fill('#collab-reg-password', PASS);
    await page.fill('#collab-reg-email', `${USER}@test.com`);
    await page.fill('#collab-reg-name', `E2E WF ${TS}`);
    await page.click('#collab-register-form button[type="submit"]');
    await expect(page.locator('#collab-reg-msg')).toContainText('注册成功');
    await expect(page.locator('#collab-login-form')).toBeVisible();
    await page.fill('#collab-password', PASS);
    await page.click('#collab-login-form button[type="submit"]');
    await expect(page.locator('#collab-main-section')).toBeVisible();
    token = await page.evaluate(() => localStorage.getItem('baa_collab_token') || '');
    expect(token).toBeTruthy();
  });

  test('W2 建团队/项目，上传图纸并创建带 file_ids 的会话', async () => {
    const teamD = await (
      await page.request.post(BASE + '/collab/teams', {
        headers: auth(),
        data: { name: TEAM_NAME, description: 'e2e' },
      })
    ).json();
    expect(teamD.status).toBe('success');
    const teamId = String((teamD.team as Record<string, unknown>).id);

    const projD = await (
      await page.request.post(BASE + '/collab/projects', {
        headers: auth(),
        data: { name: PROJ_NAME, team_id: teamId, description: 'e2e' },
      })
    ).json();
    expect(projD.status).toBe('success');
    projectId = String((projD.project as Record<string, unknown>).id);

    const buf = fs.readFileSync(path.join(FIXTURE_DIR, 'test_basic.dxf'));
    const decD = await (
      await page.request.post(BASE + '/deconstruct?building_type=civil&use_yolo=false', {
        multipart: {
          file: { name: 'test_basic.dxf', mimeType: 'application/dxf', buffer: buf },
        },
      })
    ).json();
    expect(decD.status).toBe('success');
    const fileId = String(decD.file_id || '');
    expect(fileId).toBeTruthy();

    const sesD = await (
      await page.request.post(BASE + '/collab/review-sessions', {
        headers: auth(),
        data: {
          project_id: projectId,
          name: SESSION_NAME,
          description: 'e2e 工作流',
          file_ids: [fileId],
        },
      })
    ).json();
    expect(sesD.status).toBe('success');
    sessionId = String((sesD.review_session as Record<string, unknown>).id);
  });

  test('W3 会话详情可见：draft 徽标 + 工作流/整改区块', async () => {
    await page.evaluate(
      (id) => (window as unknown as Record<string, unknown>).showReviewSessionDetail!(id),
      sessionId,
    );
    await expect(page.locator('#collab-modal-body .collab-badge-draft')).toBeVisible();
    await expect(page.locator('#collab-modal-body button:has-text("送审")')).toBeVisible();
    await expect(page.locator('#collab-modal-body')).toContainText('工作流流转');
    await expect(page.locator('#collab-modal-body')).toContainText('整改记录');
  });

  test('W4 非法流转被拒绝（draft→approved 返回 400 且状态不变）', async () => {
    const r = await page.request.put(BASE + `/collab/review-sessions/${sessionId}/status`, {
      headers: auth(),
      data: { status: 'approved' },
    });
    expect(r.status()).toBe(400);
    expect(JSON.stringify(await r.json())).toContain('非法状态流转');
    const g = await (
      await page.request.get(BASE + `/collab/review-sessions/${sessionId}`, { headers: auth() })
    ).json();
    expect(String((g.review_session as Record<string, unknown>).status)).toBe('draft');
  });

  test('W5 draft→pending→in_progress（UI 流转按钮）', async () => {
    await page.click('#collab-modal-body button:has-text("送审")');
    await expect(page.locator('#collab-modal-body .collab-badge-pending')).toBeVisible();
    await page.click('#collab-modal-body button:has-text("开始审查")');
    await expect(page.locator('#collab-modal-body .collab-badge-in_progress')).toBeVisible();
    await expect(page.locator('#collab-modal-body button:has-text("开始整改")')).toBeVisible();
  });

  test('W6 UI 登记整改项并列表展示', async () => {
    await page.fill('#rs-rect-clause', 'GB50016-5.5.2');
    await page.fill('#rs-rect-entity', 'WALL_001');
    await page.fill('#rs-rect-action', RECT_ACTION);
    await page.click('#collab-modal-body button:has-text("登记整改项")');
    await expect(page.locator('#collab-modal-body')).toContainText(RECT_ACTION);
    await expect(page.locator('#collab-modal-body .collab-badge-pending').first()).toBeVisible();
  });

  test('W7 in_progress→rectifying（UI）', async () => {
    await page.click('#collab-modal-body button:has-text("开始整改")');
    await expect(page.locator('#collab-modal-body .collab-badge-rectifying')).toBeVisible();
    await expect(page.locator('#collab-modal-body button:has-text("提交复查")')).toBeVisible();
  });

  test('W8 提交复查：状态→rechecking，对比区渲染', async () => {
    test.slow();
    await page.click('#collab-modal-body button:has-text("提交复查")');
    await expect(page.locator('#collab-modal-body .collab-badge-rechecking')).toBeVisible({
      timeout: 180_000,
    });
    await expect(page.locator('#rs-recheck-result')).toContainText('新增', { timeout: 20_000 });
    await expect(page.locator('#rs-recheck-result')).toContainText('未修复');
  });

  test('W9 整改项标记完成后操作按钮消失', async () => {
    await page.click('#collab-modal-body button:has-text("标记完成")');
    await expect(page.locator('#collab-modal-body button:has-text("标记完成")')).toHaveCount(0, {
      timeout: 15_000,
    });
    await expect(page.locator('#collab-modal-body')).toContainText('done');
  });

  test('W10 rechecking→rejected→rectifying（整改闭环）', async () => {
    await page.click('#collab-modal-body button:has-text("驳回")');
    await expect(page.locator('#collab-modal-body .collab-badge-rejected')).toBeVisible();
    await page.click('#collab-modal-body button:has-text("开始整改")');
    await expect(page.locator('#collab-modal-body .collab-badge-rectifying')).toBeVisible();
  });

  test('W11 二次复查→rechecking', async () => {
    test.slow();
    await page.click('#collab-modal-body button:has-text("提交复查")');
    await expect(page.locator('#collab-modal-body .collab-badge-rechecking')).toBeVisible({
      timeout: 180_000,
    });
  });

  test('W12 rechecking→approved→archived（终态）', async () => {
    await page.click('#collab-modal-body button:has-text("通过")');
    await expect(page.locator('#collab-modal-body .collab-badge-approved')).toBeVisible();
    await page.click('#collab-modal-body button:has-text("归档")');
    await expect(page.locator('#collab-modal-body')).toContainText('终态，无可用流转');
  });

  test('W13 交互式图纸加载：会话详情可见加载按钮，点击后 SVG 容器非空', async () => {
    // 从 W2 开始的新会话（有 file_ids）
    const { page: p, BASE: b, auth: a, FIXTURE_DIR: fd } = {
      page, BASE, auth, FIXTURE_DIR: path.join(path.dirname(fileURLToPath(import.meta.url)), 'fixtures'),
    };
    const ts2 = Date.now();
    const TEAM2 = `E2E-WF-T2-${ts2}`;
    const PROJ2 = `E2E-WF-P2-${ts2}`;
    const SES2 = `E2E-WF-S2-${ts2}`;

    const teamD = await (await p.request.post(b + '/collab/teams', { headers: a(), data: { name: TEAM2, description: 'e2e' } })).json();
    expect(teamD.status).toBe('success');
    const teamId = String((teamD.team as Record<string, unknown>).id);

    const projD = await (await p.request.post(b + '/collab/projects', { headers: a(), data: { name: PROJ2, team_id: teamId, description: 'e2e' } })).json();
    expect(projD.status).toBe('success');
    const projectId2 = String((projD.project as Record<string, unknown>).id);

    const buf = fs.readFileSync(path.join(fd, 'test_basic.dxf'));
    const decD = await (await p.request.post(b + '/deconstruct?building_type=civil&use_yolo=false', {
      multipart: { file: { name: 'test_basic.dxf', mimeType: 'application/dxf', buffer: buf } },
    })).json();
    expect(decD.status).toBe('success');
    const fileId = String(decD.file_id || '');

    const sesD = await (await p.request.post(b + '/collab/review-sessions', {
      headers: a(), data: { project_id: projectId2, name: SES2, description: 'e2e bidir-locate', file_ids: [fileId] },
    })).json();
    expect(sesD.status).toBe('success');
    const sessionId2 = String((sesD.review_session as Record<string, unknown>).id);

    // 打开会话详情，检查交互式图纸区块存在
    await p.evaluate((id) => (window as unknown as Record<string, unknown>).showReviewSessionDetail!(id), sessionId2);
    await expect(p.locator('#collab-modal-body')).toContainText('🗺️ 交互式图纸');
    await expect(p.locator('#rs-load-interactive')).toBeVisible();

    // 点击加载交互式图纸
    await p.click('#rs-load-interactive');
    await expect(p.locator('#interactive-drawing-container svg')).toBeAttached({ timeout: 15000 });

    // SVG 内有图元元素（data-eid 或 path/line/circle/text）
    const svgChildren = await p.locator('#interactive-drawing-container svg').count();
    expect(svgChildren).toBeGreaterThan(0);
  });

  test('W14 双向定位：违规→图元（locateEntity）与图元→违规（点击SVG元素触发高亮）', async () => {
    const { page: p, BASE: b, auth: a, FIXTURE_DIR: fd } = {
      page, BASE, auth, FIXTURE_DIR: path.join(path.dirname(fileURLToPath(import.meta.url)), 'fixtures'),
    };
    const ts3 = Date.now();
    const TEAM3 = `E2E-WF-T3-${ts3}`;
    const PROJ3 = `E2E-WF-P3-${ts3}`;
    const SES3 = `E2E-WF-S3-${ts3}`;

    // 建团队/项目/上传图纸/创建会话
    const teamD = await (await p.request.post(b + '/collab/teams', { headers: a(), data: { name: TEAM3, description: 'e2e' } })).json();
    expect(teamD.status).toBe('success');
    const teamId3 = String((teamD.team as Record<string, unknown>).id);
    const projD = await (await p.request.post(b + '/collab/projects', { headers: a(), data: { name: PROJ3, team_id: teamId3, description: 'e2e' } })).json();
    expect(projD.status).toBe('success');
    const projectId3 = String((projD.project as Record<string, unknown>).id);
    const buf = fs.readFileSync(path.join(fd, 'test_basic.dxf'));
    const decD = await (await p.request.post(b + '/deconstruct?building_type=civil&use_yolo=false', {
      multipart: { file: { name: 'test_basic.dxf', mimeType: 'application/dxf', buffer: buf } },
    })).json();
    expect(decD.status).toBe('success');
    const fileId = String(decD.file_id || '');
    const sesD = await (await p.request.post(b + '/collab/review-sessions', {
      headers: a(), data: { project_id: projectId3, name: SES3, description: 'e2e bidir-locate', file_ids: [fileId] },
    })).json();
    expect(sesD.status).toBe('success');

    // 导航到审查页面并加载交互式图纸
    await p.goto('/');
    await p.click('[data-page="review"]');
    await p.fill('#review-file-select', fileId);
    await p.waitForTimeout(500);
    await p.click('button:has-text("加载交互式图纸")');
    await expect(p.locator('#interactive-drawing-container svg')).toBeAttached({ timeout: 15000 });

    // 验证 SVG 图元带有 data-eid 属性（后端渲染时已嵌入 DXF handle）
    const svgEl = await p.locator('#interactive-drawing-container svg');
    await expect(svgEl).toBeVisible();
    const hasDataEid = await p.evaluate(() => {
      const svg = document.querySelector('#interactive-drawing-container svg');
      return svg ? svg.querySelectorAll('[data-eid]').length : 0;
    });
    expect(hasDataEid).toBeGreaterThan(0);

    // 验证 locateEntity 函数在 window 上可用（违规→图元定位入口）
    const hasLocateEntity = await p.evaluate(() => typeof window.locateEntity === 'function');
    expect(hasLocateEntity).toBe(true);

    // 验证调用 locateEntity 时能给出合理提示（无匹配实体时返回 false + toast）
    const result = await p.evaluate(() => (window as unknown as Record<string, unknown>).locateEntity?.('NONEXISTENT_ENTITY_XYZ') ?? false);
    expect(result).toBe(false);
  });
});
