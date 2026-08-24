// ── P123 Step 3: Collab 协作组件 ─────────────────────────
// 从 baa-admin.js lines 706-996 迁入 — 22 个函数

import { getApiBase } from '../core/api-client';
import { showToast } from '../core/toast';
import { escHtml as esc, escHtml } from '../core/utils';

let _token = localStorage.getItem('baa_collab_token') || '';
let _user: Record<string, unknown> = {};
try { _user = JSON.parse(localStorage.getItem('baa_collab_user') || '{}'); } catch (_) { /* ignore */ }

export function getCollabToken(): string { return _token; }
export function getCollabUser(): Record<string, unknown> { return _user; }

export function collabErrMsg(d: unknown): string {
  if (!d) return '请求失败';
  if (typeof d === 'string') return d;
  const obj = d as Record<string, unknown>;
  if (typeof obj.detail === 'string') return obj.detail;
  if (obj.detail && typeof obj.detail === 'object') {
    const det = obj.detail as Record<string, unknown>;
    return String(det.message || det.error_code || '请求失败');
  }
  return '请求失败';
}

export function collabApi(path: string, options?: Record<string, unknown>): Promise<Record<string, unknown>> {
  const opts: Record<string, unknown> = { ...options };
  const url = getApiBase() + path;
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (_token) headers['Authorization'] = 'Bearer ' + _token;
  if (opts.headers) {
    const extra = opts.headers as Record<string, string>;
    for (const k in extra) headers[k] = extra[k];
  }
  opts.headers = headers;
  return fetch(url, opts as RequestInit).then((r) => {
    if (r.status === 401 && _token && opts.autoLogout !== false) collabLogout();
    return r.json().catch(() => ({}));
  });
}

export function closeCollabModal(): void {
  const el = document.getElementById('collab-modal-overlay');
  if (el) el.style.display = 'none';
}

export function setModalBody(html: string): void {
  const el = document.getElementById('collab-modal-body');
  if (el) { el.innerHTML = html; const o = document.getElementById('collab-modal-overlay'); if (o) o.style.display = 'flex'; }
}

function _tabStyle(active: boolean): void {
  const btns = document.querySelectorAll('#collab-auth-tabs button');
  if (btns.length < 2) return;
  btns[0].className = active ? 'flex-1 px-4 py-2 rounded text-sm font-medium bg-blue-500 text-white' : 'flex-1 px-4 py-2 rounded text-sm font-medium bg-gray-100 text-gray-600';
  btns[1].className = active ? 'flex-1 px-4 py-2 rounded text-sm font-medium bg-gray-100 text-gray-600' : 'flex-1 px-4 py-2 rounded text-sm font-medium bg-blue-500 text-white';
}

export function showCollabLogin(): void {
  const f = document.getElementById('collab-login-form'); if (f) f.style.display = 'block';
  const r = document.getElementById('collab-register-form'); if (r) r.style.display = 'none';
  _tabStyle(true);
}

export function showCollabRegister(): void {
  const f = document.getElementById('collab-login-form'); if (f) f.style.display = 'none';
  const r = document.getElementById('collab-register-form'); if (r) r.style.display = 'block';
  _tabStyle(false);
}

export function collabLogin(): void {
  const u = (document.getElementById('collab-username') as HTMLInputElement)?.value?.trim() || '';
  const p = (document.getElementById('collab-password') as HTMLInputElement)?.value || '';
  if (!u || !p) { const m = document.getElementById('collab-auth-msg'); if (m) m.textContent = '请输入用户名和密码'; return; }
  collabApi('/collab/auth/login', { method: 'POST', body: JSON.stringify({ username: u, password: p }), autoLogout: false }).then((d) => {
    if (d.status === 'success') {
      _token = String(d.token || ''); _user = (d.user as Record<string, unknown>) || {};
      localStorage.setItem('baa_collab_token', _token); localStorage.setItem('baa_collab_user', JSON.stringify(_user));
      const m = document.getElementById('collab-auth-msg'); if (m) m.textContent = '';
      collabEnterMain();
    } else { const m = document.getElementById('collab-auth-msg'); if (m) m.textContent = collabErrMsg(d); }
  }).catch((e: Error) => { const m = document.getElementById('collab-auth-msg'); if (m) m.textContent = '网络错误: ' + e.message; });
}

export function collabRegister(): void {
  const u = (document.getElementById('collab-reg-username') as HTMLInputElement)?.value?.trim() || '';
  const p = (document.getElementById('collab-reg-password') as HTMLInputElement)?.value || '';
  const e = (document.getElementById('collab-reg-email') as HTMLInputElement)?.value?.trim() || '';
  const dn = (document.getElementById('collab-reg-name') as HTMLInputElement)?.value?.trim() || '';
  if (!u || !p) { const m = document.getElementById('collab-reg-msg'); if (m) m.textContent = '用户名和密码不能为空'; return; }
  if (p.length < 6) { const m = document.getElementById('collab-reg-msg'); if (m) m.textContent = '密码至少6位'; return; }
  const body: Record<string, string> = { username: u, password: p };
  if (e) { body.email = e; body.display_name = dn; }
  collabApi('/collab/auth/register', { method: 'POST', body: JSON.stringify(body), autoLogout: false }).then((d) => {
    if (d.status === 'success') {
      const m = document.getElementById('collab-reg-msg'); if (m) { m.textContent = '注册成功，请登录'; m.style.color = '#059669'; }
      showCollabLogin(); const un = document.getElementById('collab-username') as HTMLInputElement; if (un) un.value = u;
    } else { const m = document.getElementById('collab-reg-msg'); if (m) m.textContent = collabErrMsg(d); }
  }).catch((err: Error) => { const m = document.getElementById('collab-reg-msg'); if (m) m.textContent = '网络错误: ' + err.message; });
}

export function collabLogout(): void {
  _token = ''; _user = {};
  localStorage.removeItem('baa_collab_token'); localStorage.removeItem('baa_collab_user');
  updateUserStatus(false);
  const ms = document.getElementById('collab-main-section'); if (ms) ms.style.display = 'none';
  const ls = document.getElementById('collab-login-section'); if (ls) ls.style.display = 'block';
}

export function collabEnterMain(): void {
  const ls = document.getElementById('collab-login-section'); if (ls) ls.style.display = 'none';
  const ms = document.getElementById('collab-main-section'); if (ms) ms.style.display = 'block';
  const d = document.getElementById('collab-user-display'); if (d) d.textContent = '👤 ' + String(_user.display_name || _user.username || '');
  collabRefresh(); updateUserStatus(true);
}

export function updateUserStatus(loggedIn: boolean): void {
  const lo = document.getElementById('user-status-logged-out');
  const li = document.getElementById('user-status-logged-in');
  if (!lo || !li) return;
  if (loggedIn) {
    const ne = document.getElementById('user-status-name'); if (ne) ne.textContent = '👤 ' + String(_user.display_name || _user.username || '—');
    const re = document.getElementById('user-status-role'); if (re) re.textContent = String(_user.role || 'user');
  }
  lo.style.display = loggedIn ? 'none' : 'block';
  li.style.display = loggedIn ? 'flex' : 'none';
}

export function collabRefresh(): void { loadCollabStats(); loadCollabTeams(); }

export function loadCollabStats(): void {
  collabApi('/collab/stats').then((d) => {
    if (d.status !== 'success') return;
    const s = d.stats as Record<string, number>;
    const ue = document.getElementById('cs-users'); if (ue) ue.textContent = String(s.users || 0);
    const te = document.getElementById('cs-teams'); if (te) te.textContent = String(s.teams || 0);
    const pe = document.getElementById('cs-projects'); if (pe) pe.textContent = String(s.active_projects || 0);
    const se = document.getElementById('cs-sessions'); if (se) se.textContent = String(s.review_sessions || 0);
  });
}

export function loadCollabTeams(): void {
  collabApi('/collab/teams').then((d) => {
    const el = document.getElementById('collab-teams'); if (!el) return;
    if (d.status !== 'success') { el.innerHTML = '加载失败'; return; }
    const teams = (d.teams as Array<Record<string, unknown>>) || [];
    if (!teams.length) { el.innerHTML = '暂无团队'; return; }
    let h = '<table class="collab-table"><tr><th>名称</th><th>成员</th><th>角色</th><th>时间</th><th>操作</th></tr>';
    for (const t of teams) {
      h += '<tr><td><strong>' + esc(String(t.name)) + '</strong></td><td>' + String(t.member_count ?? '') + '</td><td><span class="collab-badge collab-badge-' + String(t.my_role) + '">' + String(t.my_role) + '</span></td><td>' + new Date(Number(t.created_at) * 1000).toLocaleDateString() + '</td><td><button class="text-blue-600 text-xs underline" onclick="showTeamDetail(\'' + String(t.id) + '\')">📋</button></td></tr>';
    }
    h += '</table>'; el.innerHTML = h;
  });
}

export function showCreateTeamModal(): void {
  setModalBody('<h3 class="text-lg font-bold mb-4">新建团队</h3><input id="modal-team-name" class="input w-full mb-2" placeholder="团队名称" /><textarea id="modal-team-desc" class="input w-full mb-3" placeholder="描述" rows="2"></textarea><div class="flex gap-2 justify-end"><button class="modal-btn modal-btn-secondary" onclick="closeCollabModal()">取消</button><button class="modal-btn modal-btn-primary" onclick="createTeam()">创建</button></div>');
}

export function createTeam(): void {
  const name = (document.getElementById('modal-team-name') as HTMLInputElement)?.value?.trim() || '';
  if (!name) return;
  const desc = (document.getElementById('modal-team-desc') as HTMLTextAreaElement)?.value?.trim() || '';
  collabApi('/collab/teams', { method: 'POST', body: JSON.stringify({ name, description: desc }) }).then((d) => {
    if (d.status === 'success') {
      ((window as unknown as Record<string, unknown>).setCurrentTeamId as (id?: string) => void)?.(String(d.team_id || d.id || ''));
      ((window as unknown as Record<string, unknown>).setCurrentProjectId as (id?: string) => void)?.('');
      closeCollabModal(); collabRefresh();
    } else { showToast(collabErrMsg(d), 'info'); }
  });
}

export function showTeamDetail(teamId: string): void {
  ((window as unknown as Record<string, unknown>).setCurrentTeamId as (id?: string) => void)?.(teamId);
  ((window as unknown as Record<string, unknown>).setCurrentProjectId as (id?: string) => void)?.('');
  Promise.all([collabApi('/collab/teams/' + teamId), collabApi('/collab/teams/' + teamId + '/projects')]).then((r) => {
    if (r[0].status !== 'success') return;
    const team = (r[0].team as Record<string, unknown>) || {};
    const projects = (r[1].projects as Array<Record<string, unknown>>) || [];
    const members = (team.members as Array<Record<string, unknown>>) || [];
    let mh = '<table class="collab-table"><tr><th>用户</th><th>角色</th><th>时间</th></tr>';
    for (const m of members) {
      mh += '<tr><td>' + esc(String(m.display_name || m.username || '')) + '</td><td><span class="collab-badge collab-badge-' + String(m.role) + '">' + String(m.role) + '</span></td><td>' + new Date(Number(m.joined_at) * 1000).toLocaleDateString() + '</td></tr>';
    }
    mh += '</table>';
    let ph = '';
    if (!projects.length) { ph = '<p class="text-sm text-gray-400 py-2">暂无项目</p>'; } else {
      ph = '<table class="collab-table"><tr><th>项目</th><th>图纸</th><th>审查</th><th>状态</th><th>操作</th></tr>';
      for (const p of projects) {
        ph += '<tr><td><strong>' + esc(String(p.name)) + '</strong></td><td>' + String(p.file_count ?? '') + '</td><td>' + String(p.review_count ?? '') + '</td><td>' + String(p.status) + '</td><td><button class="text-blue-600 text-xs underline" onclick="showProjectDetail(\'' + String(p.id) + '\')">📝</button></td></tr>';
      }
      ph += '</table>';
    }
    setModalBody('<h3 class="text-lg font-bold mb-4">团队: ' + esc(String(team.name)) + '</h3><div class="mb-4"><h4 class="font-medium mb-2">成员 (' + members.length + ')</h4>' + mh + '</div><div><div class="flex justify-between items-center mb-2"><h4 class="font-medium">项目</h4><button class="modal-btn modal-btn-primary text-xs" onclick="showCreateProjectModal(\'' + teamId + '\')">+ 新建项目</button></div>' + ph + '</div><div class="flex gap-2 justify-end mt-4"><button class="modal-btn modal-btn-secondary" onclick="closeCollabModal()">关闭</button></div>');
  });
}

export function showProjectDetail(projectId: string): void {
  ((window as unknown as Record<string, unknown>).setCurrentProjectId as (id?: string) => void)?.(projectId);
  Promise.all([collabApi('/collab/projects/' + projectId), collabApi('/collab/projects/' + projectId + '/review-sessions')]).then((r) => {
    if (r[0].status !== 'success') return;
    const proj = (r[0].project as Record<string, unknown>) || {};
    const sessions = (r[1].review_sessions as Array<Record<string, unknown>>) || [];
    const members = (proj.members as Array<Record<string, unknown>>) || [];
    let mh = '<table class="collab-table"><tr><th>用户</th><th>权限</th></tr>';
    for (const m of members) { mh += '<tr><td>' + esc(String(m.display_name || m.username || '')) + '</td><td><span class="collab-badge">' + String(m.permission) + '</span></td></tr>'; }
    mh += '</table>';
    let sh = '';
    if (!sessions.length) { sh = '<p class="text-sm text-gray-400 py-2">暂无审查会话</p>'; } else {
      sh = '<table class="collab-table"><tr><th>名称</th><th>状态</th><th>创建人</th><th>时间</th><th>操作</th></tr>';
      for (const s of sessions) {
        sh += '<tr><td>' + esc(String(s.name)) + '</td><td><span class="collab-badge collab-badge-' + String(s.status) + '">' + String(s.status) + '</span></td><td>' + esc(String(s.creator_name || '')) + '</td><td>' + new Date(Number(s.created_at) * 1000).toLocaleString() + '</td><td><button class="text-blue-600 text-xs underline" onclick="showReviewSessionDetail(\'' + String(s.id) + '\')">📝</button></td></tr>';
      }
      sh += '</table>';
    }
    setModalBody('<h3 class="text-lg font-bold mb-4">项目: ' + esc(String(proj.name)) + '</h3><div class="mb-4"><h4 class="font-medium mb-2">成员</h4>' + mh + '</div><div><div class="flex justify-between items-center mb-2"><h4 class="font-medium">审查会话</h4><button class="modal-btn modal-btn-primary text-xs" onclick="showCreateReviewSessionModal(\'' + projectId + '\' )">+ 新建审查</button></div>' + sh + '</div><div class="flex gap-2 justify-end mt-4"><button class="modal-btn modal-btn-secondary" onclick="closeCollabModal()">关闭</button></div>');
  });
}

export function showCreateProjectModal(teamId: string): void {
  setModalBody('<h3 class="text-lg font-bold mb-4">新建项目</h3><input id="modal-proj-name" class="input w-full mb-2" placeholder="项目名称" /><textarea id="modal-proj-desc" class="input w-full mb-2" placeholder="描述" rows="2"></textarea><input id="modal-proj-type" class="input w-full mb-2" placeholder="建筑类型" /><div class="flex gap-2 justify-end"><button class="modal-btn modal-btn-secondary" onclick="showTeamDetail(\'' + teamId + '\' )">返回</button><button class="modal-btn modal-btn-primary" onclick="createProject(\'' + teamId + '\' )">创建</button></div>');
}

export function createProject(teamId: string): void {
  const name = (document.getElementById('modal-proj-name') as HTMLInputElement)?.value?.trim() || '';
  if (!name) return;
  const desc = (document.getElementById('modal-proj-desc') as HTMLTextAreaElement)?.value?.trim() || '';
  const btype = (document.getElementById('modal-proj-type') as HTMLInputElement)?.value?.trim() || '';
  collabApi('/collab/projects', { method: 'POST', body: JSON.stringify({ name, team_id: teamId, description: desc, building_type: btype }) }).then((d) => {
    if (d.status === 'success') {
      ((window as unknown as Record<string, unknown>).setCurrentTeamId as (id?: string) => void)?.(teamId);
      ((window as unknown as Record<string, unknown>).setCurrentProjectId as (id?: string) => void)?.(String(d.project_id || d.id || ''));
      showTeamDetail(teamId);
    } else { showToast(collabErrMsg(d), 'info'); }
  });
}

export function showCreateReviewSessionModal(projectId: string): void {
  setModalBody('<h3 class="text-lg font-bold mb-4">新建审查会话</h3><input id="modal-rs-name" class="input w-full mb-2" placeholder="名称" /><textarea id="modal-rs-desc" class="input w-full mb-2" placeholder="描述" rows="2"></textarea><div class="flex gap-2 justify-end"><button class="modal-btn modal-btn-secondary" onclick="showProjectDetail(\'' + projectId + '\' )">返回</button><button class="modal-btn modal-btn-primary" onclick="createReviewSession(\'' + projectId + '\' )">创建</button></div>');
}

export function createReviewSession(projectId: string): void {
  const name = (document.getElementById('modal-rs-name') as HTMLInputElement)?.value?.trim() || '';
  if (!name) return;
  const desc = (document.getElementById('modal-rs-desc') as HTMLTextAreaElement)?.value?.trim() || '';
  collabApi('/collab/review-sessions', { method: 'POST', body: JSON.stringify({ project_id: projectId, name, description: desc }) }).then((d) => {
    if (d.status === 'success') { showProjectDetail(projectId); } else { showToast(collabErrMsg(d), 'info'); }
  });
}

export function showReviewSessionDetail(sessionId: string): void {
  Promise.all([
    collabApi('/collab/review-sessions/' + sessionId),
    collabApi('/collab/review-sessions/' + sessionId + '/comments'),
    collabApi('/collab/review-sessions/' + sessionId + '/approval-flow')
  ]).then((r) => {
    if (r[0].status !== 'success') return;
    const rs = (r[0].review_session as Record<string, unknown>) || {};
    const comments = (r[1].comments as Array<Record<string, unknown>>) || [];
    const flow = r[2].approval_flow as { steps?: Array<Record<string, unknown>> } | undefined;
    const statusBadge = '<span class="collab-badge collab-badge-' + String(rs.status) + '">' + String(rs.status) + '</span>';
    let ch = '';
    if (!comments.length) { ch = '<p class="text-sm text-gray-400 py-2">暂无评论</p>'; } else {
      for (const c of comments) {
        const icon = c.comment_type === 'issue' ? '⚠️' : c.comment_type === 'suggestion' ? '💡' : c.comment_type === 'question' ? '❓' : '✅';
        ch += '<div class="comment-box comment-' + String(c.comment_type) + '"><div class="flex justify-between items-start"><span class="font-medium text-sm">' + icon + ' ' + escHtml(String(c.author_name || '')) + '</span><span class="text-xs text-gray-400">' + new Date(Number(c.created_at) * 1000).toLocaleString() + '</span></div><p class="text-sm mt-1">' + escHtml(String(c.content || '')) + '</p>';
        if (c.clause_ref) { ch += '<div class="text-xs text-gray-400 mt-1">• 条款: ' + escHtml(String(c.clause_ref)) + '</div>'; }
        if (c.entity_ref) { ch += '<div class="text-xs text-gray-400">• 实体: ' + escHtml(String(c.entity_ref)) + '</div>'; }
        ch += '</div>';
      }
    }
    let fh = '';
    if (flow && flow.steps) {
      fh = '<table class="collab-table"><tr><th>序号</th><th>审批人</th><th>状态</th><th>意见</th><th>时间</th></tr>';
      for (const st of flow.steps) {
        const sb = '<span class="collab-badge collab-badge-' + String(st.status) + '">' + String(st.status) + '</span>';
        fh += '<tr><td>' + String(st.order) + '</td><td>' + escHtml(String(st.reviewer_name || '')) + '</td><td>' + sb + '</td><td>' + escHtml(String(st.comment || '')) + '</td><td>' + (st.acted_at ? new Date(Number(st.acted_at) * 1000).toLocaleString() : '') + '</td></tr>';
      }
      fh += '</table>';
    } else {
      fh = '<p class="text-sm text-gray-400 py-2">暂无审批流程</p>';
    }
    setModalBody('<h3 class="text-lg font-bold mb-4">审查会话: ' + escHtml(String(rs.name || '')) + ' ' + statusBadge + '</h3><div class="mb-4"><h4 class="font-medium mb-2">评论</h4>' + ch + '</div><div><h4 class="font-medium mb-2">审批流程</h4>' + fh + '</div><div class="flex gap-2 justify-end mt-4"><button class="modal-btn modal-btn-secondary" onclick="closeCollabModal()">关闭</button></div>');
  });
}

// P43 auto-login: 模块加载时检查已有 token，有效则进入主区
if (_token) {
  setTimeout(() => {
    collabApi('/collab/users/me', { autoLogout: false }).then((d) => {
      if (d.status === 'success') {
        _user = (d.user as Record<string, unknown>) || {};
        localStorage.setItem('baa_collab_user', JSON.stringify(_user));
        updateUserStatus(true);
        const page = document.getElementById('page-collab');
        if (page && page.classList.contains('active')) {
          collabEnterMain();
        } else {
          const mainSec = document.getElementById('collab-main-section');
          const loginSec = document.getElementById('collab-login-section');
          if (mainSec && loginSec) { mainSec.style.display = 'block'; loginSec.style.display = 'none'; }
        }
      } else { collabLogout(); }
    }).catch(() => { collabLogout(); });
  }, 500);
}
