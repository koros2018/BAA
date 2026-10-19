// T-B5 协作前端收尾 — 全流程 E2E（认证 → 团队 → 评论 → 审批）
// 运行： npx playwright test -c tests/e2e/playwright.config.ts test_collab_flow
import { test, expect, type Page, type BrowserContext } from '@playwright/test';

const BASE = 'http://127.0.0.1:8000';
const TS = Date.now();
const USER_A = `e2eflow_a_${TS}`;
const USER_B = `e2eflow_b_${TS}`;
const PASS = 'P@ssw0rd!';
const TEAM_NAME = `E2E团队_${TS}`;
const PROJ_NAME = `E2E项目_${TS}`;
const SESSION_NAME = `E2E审查_${TS}`;
const COMMENT_TEXT = 'E2E 测试评论内容';

let context: BrowserContext;
let page: Page;
let teamId = '';
let projectId = '';
let sessionId = '';

async function getToken(): Promise<string> {
  return await page.evaluate(() => localStorage.getItem('baa_collab_token') || '');
}

async function authGet(path: string): Promise<Record<string, unknown>> {
  const t = await getToken();
  const r = await page.request.get(BASE + path, { headers: { Authorization: 'Bearer ' + t } });
  return (await r.json()) as Record<string, unknown>;
}

test.describe.serial('协作全流程 E2E（认证→团队→评论→审批）', () => {
  test.beforeAll(async ({ browser }) => {
    context = await browser.newContext();
    page = await context.newPage();
  });

  test.afterAll(async () => {
    await context.close();
  });

  test('C1 注册并登录用户A', async () => {
    await page.goto('/');
    await page.click('[data-page="collab"]');
    await expect(page.locator('#collab-login-section')).toBeVisible();

    await page.click('#collab-auth-tabs button:nth-child(2)');
    await expect(page.locator('#collab-register-form')).toBeVisible();
    await page.fill('#collab-reg-username', USER_A);
    await page.fill('#collab-reg-password', PASS);
    await page.fill('#collab-reg-email', `${USER_A}@test.com`);
    await page.fill('#collab-reg-name', `E2E A ${TS}`);
    await page.click('#collab-register-form button[type="submit"]');
    await expect(page.locator('#collab-reg-msg')).toContainText('注册成功');

    await expect(page.locator('#collab-login-form')).toBeVisible();
    await page.fill('#collab-password', PASS);
    await page.click('#collab-login-form button[type="submit"]');
    await expect(page.locator('#collab-main-section')).toBeVisible();
    await expect(page.locator('#collab-user-display')).toContainText(`E2E A ${TS}`);
  });

  test('C2 创建团队', async () => {
    await page.click('button[data-action="showCreateTeamModal"]');
    await expect(page.locator('#modal-team-name')).toBeVisible();
    await page.fill('#modal-team-name', TEAM_NAME);
    await page.fill('#modal-team-desc', 'E2E 自动化创建');
    await page.click('#collab-modal-body button:has-text("创建")');
    await expect(page.locator('#collab-teams')).toContainText(TEAM_NAME);
  });

  test('C3 注册用户B并添加为团队成员', async () => {
    const reg = await page.request.post(BASE + '/collab/auth/register', {
      data: {
        username: USER_B,
        password: PASS,
        email: `${USER_B}@test.com`,
        display_name: `E2E B ${TS}`,
      },
    });
    expect(reg.ok()).toBeTruthy();

    const teams = await authGet('/collab/teams');
    const team = ((teams.teams as Array<Record<string, unknown>>) || []).find(
      (t) => t.name === TEAM_NAME,
    );
    expect(team).toBeTruthy();
    teamId = String(team!.id);

    await page.evaluate((id) => (window as unknown as Record<string, unknown>).showTeamDetail!(id), teamId);
    await expect(page.locator('#collab-modal-body')).toContainText('成员');
    await page.click('#collab-modal-body button:has-text("添加成员")');
    await page.fill('#member-search', USER_B);
    await page.click('#collab-modal-body button:has-text("搜索")');
    await expect(page.locator('#member-results')).toContainText(`E2E B ${TS}`);
    await page.click('#member-results button:has-text("添加")');
    await expect(page.locator('#collab-modal-body')).toContainText(`E2E B ${TS}`);
  });

  test('C4 创建项目', async () => {
    await page.click('#collab-modal-body button:has-text("新建项目")');
    await expect(page.locator('#modal-proj-name')).toBeVisible();
    await page.fill('#modal-proj-name', PROJ_NAME);
    await page.fill('#modal-proj-desc', 'E2E 项目');
    await page.click('#collab-modal-body button:has-text("创建")');
    await expect(page.locator('#collab-modal-body')).toContainText(PROJ_NAME);
  });

  test('C5 创建审查会话', async () => {
    const projects = await authGet('/collab/teams/' + teamId + '/projects');
    const proj = ((projects.projects as Array<Record<string, unknown>>) || []).find(
      (p) => p.name === PROJ_NAME,
    );
    expect(proj).toBeTruthy();
    projectId = String(proj!.id);

    await page.evaluate(
      (id) => (window as unknown as Record<string, unknown>).showProjectDetail!(id),
      projectId,
    );
    await expect(page.locator('#collab-modal-body')).toContainText('审查会话');
    await page.click('#collab-modal-body button:has-text("新建审查")');
    await page.fill('#modal-rs-name', SESSION_NAME);
    await page.fill('#modal-rs-desc', 'E2E 审查');
    await page.click('#collab-modal-body button:has-text("创建")');
    await expect(page.locator('#collab-modal-body')).toContainText(SESSION_NAME);
  });

  test('C6 打开审查会话详情，评论与审批区域可见', async () => {
    const sessions = await authGet('/collab/projects/' + projectId + '/review-sessions');
    const s = ((sessions.review_sessions as Array<Record<string, unknown>>) || []).find(
      (x) => x.name === SESSION_NAME,
    );
    expect(s).toBeTruthy();
    sessionId = String(s!.id);

    await page.evaluate(
      (id) => (window as unknown as Record<string, unknown>).showReviewSessionDetail!(id),
      sessionId,
    );
    await expect(page.locator('#rs-comment-content')).toBeVisible();
    await expect(page.locator('#rs-approval-create')).toBeVisible();
  });

  test('C7 发表评论（含条款/实体）', async () => {
    await page.fill('#rs-comment-content', COMMENT_TEXT);
    await page.fill('#rs-comment-clause', 'GB50016-5.3.1');
    await page.fill('#rs-comment-entity', 'WALL_1');
    await page.click('#collab-modal-body button:has-text("发表评论")');
    await expect(page.locator('#collab-modal-body')).toContainText(COMMENT_TEXT);
    await expect(page.locator('#collab-modal-body')).toContainText('GB50016-5.3.1');
  });

  test('C8 标记评论已解决', async () => {
    await page.click('#collab-modal-body button:has-text("标记已解决")');
    await expect(page.locator('#collab-modal-body')).toContainText('已解决');
  });

  test('C9 发起审批流程', async () => {
    const uid = await page.evaluate(
      () =>
        ((JSON.parse(localStorage.getItem('baa_collab_user') || '{}') as Record<string, unknown>)
          .id as string) || '',
    );
    expect(uid).toBeTruthy();
    await page.click('#rs-approval-create');
    await page.fill('#approval-assignees', uid);
    await page.click('#collab-modal-body button:has-text("提交")');
    await expect(page.locator('#collab-modal-body')).toContainText('pending');
  });

  test('C10 批准审批步骤', async () => {
    await page.click('#collab-modal-body button:has-text("通过")');
    await expect(page.locator('#collab-modal-body')).toContainText('approved');
  });
});
