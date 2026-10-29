// ── P123 Step 3: Collab 协作组件 ─────────────────────────
// 从 baa-admin.js lines 706-996 迁入 — 22 个函数

import { getApiBase } from '../core/api-client';
import { showToast } from '../core/toast';
import { escHtml as esc, escHtml } from '../core/utils';
import { loadInteractiveDrawing } from './drawing-viewer';

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
      ((window as unknown as Record<string, unknown>).setCurrentTeamId as (id?: string) => void)?.(String(((d.team as Record<string, unknown>)?.id as string) || ''));
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
    setModalBody('<h3 class="text-lg font-bold mb-4">团队: ' + esc(String(team.name)) + '</h3><div class="mb-4"><div class="flex justify-between items-center mb-2"><h4 class="font-medium">成员 (' + members.length + ')</h4><button class="modal-btn modal-btn-primary text-xs" onclick="showAddMemberModal(\'' + teamId + '\')">+ 添加成员</button></div>' + mh + '</div><div><div class="flex justify-between items-center mb-2"><h4 class="font-medium">项目</h4><button class="modal-btn modal-btn-primary text-xs" onclick="showCreateProjectModal(\'' + teamId + '\')">+ 新建项目</button></div>' + ph + '</div><div class="flex gap-2 justify-end mt-4"><button class="modal-btn modal-btn-secondary" onclick="closeCollabModal()">关闭</button></div>');
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
      ((window as unknown as Record<string, unknown>).setCurrentProjectId as (id?: string) => void)?.(String(((d.project as Record<string, unknown>)?.id as string) || ''));
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
    collabApi('/collab/review-sessions/' + sessionId + '/approval-flow'),
    collabApi('/collab/review-sessions/' + sessionId + '/rectifications')
  ]).then((r) => {
    if (r[0].status !== 'success') return;
    const rs = (r[0].review_session as Record<string, unknown>) || {};
    const comments = (r[1].comments as Array<Record<string, unknown>>) || [];
    const flow = r[2].approval_flow as { steps?: Array<Record<string, unknown>> } | undefined;
    const rects = r[3] && r[3].status === 'success' ? ((r[3].rectifications as Array<Record<string, unknown>>) || []) : [];
    const statusBadge = '<span class="collab-badge collab-badge-' + String(rs.status) + '">' + String(rs.status) + '</span>';
    const statusActions = buildStatusActions(String(rs.status || ''), sessionId);
    let ch = '';
    if (!comments.length) { ch = '<p class="text-sm text-gray-400 py-2">暂无评论</p>'; } else {
      for (const c of comments) {
        const icon = c.comment_type === 'issue' ? '⚠️' : c.comment_type === 'suggestion' ? '💡' : c.comment_type === 'question' ? '❓' : '✅';
        const resolved = c.is_resolved === true;
        ch += '<div class="comment-box comment-' + String(c.comment_type) + '" data-comment-id="' + String(c.id) + '"><div class="flex justify-between items-start"><span class="font-medium text-sm">' + icon + ' ' + escHtml(String(c.author_name || '')) + (resolved ? ' <span class="text-xs text-green-600">✅ 已解决</span>' : '') + '</span><span class="text-xs text-gray-400">' + new Date(Number(c.created_at) * 1000).toLocaleString() + '</span></div><p class="text-sm mt-1">' + escHtml(String(c.content || '')) + '</p>';
        if (c.clause_id) { ch += '<div class="text-xs text-gray-400 mt-1">• 条款: ' + escHtml(String(c.clause_id)) + '</div>'; }
        if (c.entity_id) { ch += '<div class="text-xs text-gray-400">• 实体: ' + escHtml(String(c.entity_id)) + '</div>'; }
        if (!c.is_resolved) { ch += '<div class="mt-1"><button class="text-xs text-green-700 underline" onclick="resolveComment(\'' + String(c.id) + '\', \'' + sessionId + '\')">标记已解决</button></div>'; }
        ch += '</div>';
      }
    }
    let fh = '';
    if (flow && flow.steps && flow.steps.length) {
      fh = '<table class="collab-table"><tr><th>序号</th><th>审批人</th><th>状态</th><th>意见</th><th>时间</th><th>操作</th></tr>';
      for (const st of flow.steps) {
        const sb = '<span class="collab-badge collab-badge-' + String(st.status) + '">' + String(st.status) + '</span>';
        const acts = st.status === 'pending' ? '<button class="text-xs text-green-700 underline mr-2" onclick="approveApprovalStep(\'' + String(st.id) + '\', \'' + sessionId + '\')">通过</button><button class="text-xs text-red-600 underline" onclick="showRejectStepModal(\'' + String(st.id) + '\', \'' + sessionId + '\')">驳回</button>' : '';
        fh += '<tr><td>' + String(st.step_order) + '</td><td>' + escHtml(String(st.assignee_name || '')) + '</td><td>' + sb + '</td><td>' + escHtml(String(st.comment || '')) + '</td><td>' + (st.decided_at ? new Date(Number(st.decided_at) * 1000).toLocaleString() : '') + '</td><td>' + acts + '</td></tr>';
      }
      fh += '</table>';
    } else {
      fh = '<p class="text-sm text-gray-400 py-2">暂无审批流程</p>';
    }
    const commentForm = '<div class="mt-3 border-t pt-3"><div class="flex gap-2 mb-2"><select id="rs-comment-type" class="input text-sm"><option value="issue">问题</option><option value="suggestion">建议</option><option value="question">疑问</option><option value="note">备注</option></select><input id="rs-comment-clause" class="input text-sm" placeholder="条款ID(可选)" /><input id="rs-comment-entity" class="input text-sm" placeholder="实体ID(可选)" /></div><textarea id="rs-comment-content" class="input w-full" rows="2" placeholder="评论内容"></textarea><div class="flex justify-between items-center mt-2"><span id="rs-comment-msg" class="text-xs text-red-600"></span><button class="modal-btn modal-btn-primary text-xs" onclick="submitComment(\'' + sessionId + '\')">发表评论</button></div></div>';
    const approvalTools = '<div class="mt-2"><button id="rs-approval-create" class="modal-btn modal-btn-primary text-xs" onclick="showApprovalFlowForm(\'' + sessionId + '\')">+ 发起审批</button><div id="rs-approval-form" class="mt-2"></div></div>';
    const workflowSection = '<div class="mb-4 border-t pt-3"><h4 class="font-medium mb-2">工作流流转</h4><div class="flex gap-2 flex-wrap">' + statusActions + '</div><div id="rs-recheck-result" class="mt-2"></div></div>';
    const rectSection = buildRectificationSection(sessionId, rects);
    // T-B6: 交互式图纸（session 有 file_ids 时显示）
    const fileIds = (rs.file_ids as string[] | undefined) || [];
    let drawingSection = '';
    if (fileIds.length > 0) {
      drawingSection = '<div class="mb-4 border-t pt-3"><h4 class="font-medium mb-2">🗺️ 交互式图纸</h4><div class="flex gap-2 mb-2"><button id="rs-load-interactive" class="modal-btn modal-btn-primary text-xs" onclick="loadInteractiveDrawing()">加载交互式图纸</button></div><div id="interactive-drawing-container" data-interactive-drawing="1" class="border rounded p-1 overflow-auto max-h-96 bg-white"></div></div>';
    }
    setModalBody('<h3 class="text-lg font-bold mb-4">审查会话: ' + escHtml(String(rs.name || '')) + ' ' + statusBadge + '</h3>' + workflowSection + '<div class="mb-4"><h4 class="font-medium mb-2">评论</h4>' + ch + commentForm + '</div>' + rectSection + drawingSection + '<div><h4 class="font-medium mb-2">审批流程</h4>' + fh + approvalTools + '</div><div class="flex gap-2 justify-end mt-4"><button class="modal-btn modal-btn-secondary" onclick="closeCollabModal()">关闭</button></div>');
  });
}

export function submitComment(sessionId: string): void {
  const content = (document.getElementById('rs-comment-content') as HTMLTextAreaElement)?.value?.trim() || '';
  if (!content) { const m = document.getElementById('rs-comment-msg'); if (m) m.textContent = '评论内容不能为空'; return; }
  const commentType = (document.getElementById('rs-comment-type') as HTMLSelectElement)?.value || 'note';
  const clauseId = (document.getElementById('rs-comment-clause') as HTMLInputElement)?.value?.trim() || '';
  const entityId = (document.getElementById('rs-comment-entity') as HTMLInputElement)?.value?.trim() || '';
  collabApi('/collab/review-sessions/' + sessionId + '/comments', { method: 'POST', body: JSON.stringify({ content, comment_type: commentType, clause_id: clauseId, entity_id: entityId }) }).then((d) => {
    if (d.status === 'success') { showReviewSessionDetail(sessionId); } else { const m = document.getElementById('rs-comment-msg'); if (m) m.textContent = collabErrMsg(d); }
  });
}

export function resolveComment(commentId: string, sessionId: string): void {
  collabApi('/collab/comments/' + commentId + '/resolve', { method: 'PUT' }).then((d) => {
    if (d.status === 'success') { showReviewSessionDetail(sessionId); } else { showToast(collabErrMsg(d), 'info'); }
  });
}

export function showApprovalFlowForm(sessionId: string): void {
  const el = document.getElementById('rs-approval-form'); if (!el) return;
  el.innerHTML = '<input id="approval-name" class="input w-full mb-2 text-sm" value="标准审批" placeholder="审批流程名称" /><input id="approval-assignees" class="input w-full mb-2 text-sm" placeholder="审批人用户ID(逗号分隔)" /><div class="flex gap-2 justify-end"><button class="modal-btn modal-btn-secondary text-xs" onclick="document.getElementById(\'rs-approval-form\').innerHTML=\'\'">取消</button><button class="modal-btn modal-btn-primary text-xs" onclick="createApprovalFlow(\'' + sessionId + '\')">提交</button></div>';
}

export function createApprovalFlow(sessionId: string): void {
  const name = (document.getElementById('approval-name') as HTMLInputElement)?.value?.trim() || '标准审批';
  const raw = (document.getElementById('approval-assignees') as HTMLInputElement)?.value?.trim() || '';
  const assigneeIds = raw.split(',').map((s) => s.trim()).filter((s) => s.length > 0);
  if (!assigneeIds.length) { showToast('请填写审批人用户ID', 'info'); return; }
  collabApi('/collab/review-sessions/' + sessionId + '/approval-flow', { method: 'POST', body: JSON.stringify({ name, assignee_ids: assigneeIds }) }).then((d) => {
    if (d.status === 'success') { showReviewSessionDetail(sessionId); } else { showToast(collabErrMsg(d), 'info'); }
  });
}

export function approveApprovalStep(stepId: string, sessionId: string): void {
  collabApi('/collab/approval-steps/' + stepId + '/approve', { method: 'POST', body: JSON.stringify({ comment: '' }) }).then((d) => {
    if (d.status === 'success') { showReviewSessionDetail(sessionId); } else { showToast(collabErrMsg(d), 'info'); }
  });
}

export function showRejectStepModal(stepId: string, sessionId: string): void {
  setModalBody('<h3 class="text-lg font-bold mb-4">驳回审批</h3><textarea id="reject-comment" class="input w-full mb-2" rows="3" placeholder="驳回意见"></textarea><div class="flex gap-2 justify-end"><button class="modal-btn modal-btn-secondary" onclick="showReviewSessionDetail(\'' + sessionId + '\')">返回</button><button class="modal-btn modal-btn-primary" onclick="rejectApprovalStep(\'' + stepId + '\', \'' + sessionId + '\')">确认驳回</button></div>');
}

export function rejectApprovalStep(stepId: string, sessionId: string): void {
  const comment = (document.getElementById('reject-comment') as HTMLTextAreaElement)?.value?.trim() || '';
  collabApi('/collab/approval-steps/' + stepId + '/reject', { method: 'POST', body: JSON.stringify({ comment }) }).then((d) => {
    if (d.status === 'success') { showReviewSessionDetail(sessionId); } else { showToast(collabErrMsg(d), 'info'); }
  });
}

export function updateSessionStatus(sessionId: string, status: string): void {
  collabApi('/collab/review-sessions/' + sessionId + '/status', { method: 'PUT', body: JSON.stringify({ status }) }).then((d) => {
    if (d.status === 'success') { showReviewSessionDetail(sessionId); } else { showToast(collabErrMsg(d), 'info'); }
  });
}

export function showAddMemberModal(teamId: string): void {
  setModalBody('<h3 class="text-lg font-bold mb-4">添加团队成员</h3><div class="flex gap-2 mb-2"><input id="member-search" class="input flex-1" placeholder="搜索用户名" /><select id="member-role" class="input text-sm"><option value="member">member</option><option value="manager">manager</option><option value="guest">guest</option></select><button class="modal-btn modal-btn-primary text-xs" onclick="searchUsersForMember(\'' + teamId + '\')">搜索</button></div><div id="member-results"></div><div class="flex gap-2 justify-end mt-4"><button class="modal-btn modal-btn-secondary" onclick="showTeamDetail(\'' + teamId + '\')">返回</button></div>');
}

export function searchUsersForMember(teamId: string): void {
  const q = (document.getElementById('member-search') as HTMLInputElement)?.value?.trim() || '';
  collabApi('/collab/users/search?query=' + encodeURIComponent(q)).then((d) => {
    const el = document.getElementById('member-results'); if (!el) return;
    const users = (d.users as Array<Record<string, unknown>>) || [];
    if (!users.length) { el.innerHTML = '<p class="text-sm text-gray-400 py-2">无匹配用户</p>'; return; }
    let h = '<table class="collab-table"><tr><th>用户</th><th>操作</th></tr>';
    for (const u of users) {
      h += '<tr><td>' + escHtml(String(u.display_name || u.username || '')) + '</td><td><button class="text-blue-600 text-xs underline" onclick="addTeamMember(\'' + teamId + '\', \'' + String(u.id) + '\')">添加</button></td></tr>';
    }
    h += '</table>'; el.innerHTML = h;
  });
}

export function addTeamMember(teamId: string, userId: string): void {
  const role = (document.getElementById('member-role') as HTMLSelectElement)?.value || 'member';
  collabApi('/collab/teams/' + teamId + '/members', { method: 'POST', body: JSON.stringify({ user_id: userId, role }) }).then((d) => {
    if (d.status === 'success') { showTeamDetail(teamId); } else { showToast(collabErrMsg(d), 'info'); }
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


// ── T-B6: 工作流闭环（状态流转按钮 / 整改记录 / 复查对比） ─────────────

/** 按当前状态渲染合法流转按钮（与后端 REVIEW_STATUS_TRANSITIONS 对应） */
function buildStatusActions(status: string, sessionId: string): string {
  const sBtn = (label: string, target: string, cls: string) =>
    '<button class="px-2 py-1 rounded text-xs ' + cls + '" onclick="updateSessionStatus(\'' + sessionId + '\', \'' + target + '\')">' + label + '</button>';
  const reBtn =
    '<button class="px-2 py-1 rounded text-xs bg-indigo-600 text-white hover:bg-indigo-700" onclick="recheckSession(\'' + sessionId + '\')">🔍 提交复查</button>';
  switch (status) {
    case 'draft':
      return sBtn('📤 送审', 'pending', 'bg-blue-600 text-white hover:bg-blue-700');
    case 'pending':
      return sBtn('▶ 开始审查', 'in_progress', 'bg-blue-600 text-white hover:bg-blue-700');
    case 'in_progress':
      return sBtn('✅ 通过', 'approved', 'bg-green-600 text-white hover:bg-green-700') +
        sBtn('❌ 驳回', 'rejected', 'bg-red-600 text-white hover:bg-red-700') +
        sBtn('🔧 开始整改', 'rectifying', 'bg-orange-500 text-white hover:bg-orange-600');
    case 'rejected':
      return sBtn('🔧 开始整改', 'rectifying', 'bg-orange-500 text-white hover:bg-orange-600');
    case 'rectifying':
      return reBtn;
    case 'rechecking':
      return sBtn('✅ 通过', 'approved', 'bg-green-600 text-white hover:bg-green-700') +
        sBtn('❌ 驳回', 'rejected', 'bg-red-600 text-white hover:bg-red-700');
    case 'approved':
      return sBtn('📦 归档', 'archived', 'bg-gray-600 text-white hover:bg-gray-700');
    default:
      return '<span class="text-xs text-gray-400">终态，无可用流转</span>';
  }
}

/** 复查对比结果渲染到 #rs-recheck-result */
function showRecheckResult(d: Record<string, unknown>): void {
  const box = document.getElementById('rs-recheck-result');
  if (!box) return;
  const cmp = (d.comparison as Record<string, any>) || {};
  const cnt = (k: string) => Number((cmp[k] && cmp[k].count) || 0);
  const items = (k: string) =>
    (((cmp[k] && cmp[k].items) || []) as Array<Record<string, unknown>>)
      .slice(0, 8)
      .map((it) =>
        '<li class="truncate">' + escHtml(String(it.clause_title || it.clause_id || '-')) +
        (it.entity_id ? ' @' + escHtml(String(it.entity_id)) : '') + '</li>'
      )
      .join('');
  box.innerHTML =
    '<div class="text-xs bg-gray-50 border rounded p-2 mt-2">' +
    '<div class="flex gap-3 mb-1">' +
    '<span class="text-green-700 font-medium">✅ 已解决 ' + cnt('resolved') + '</span>' +
    '<span class="text-red-700 font-medium">🆕 新增 ' + cnt('new') + '</span>' +
    '<span class="text-orange-600 font-medium">🔁 未修复 ' + cnt('persisted') + '</span>' +
    '<span class="text-gray-500">共 ' + Number(d.findings_count || 0) + ' 条违规</span>' +
    '</div>' +
    '<div class="grid grid-cols-3 gap-2">' +
    '<ul class="list-disc pl-4 text-gray-500">' + items('resolved') + '</ul>' +
    '<ul class="list-disc pl-4 text-gray-500">' + items('new') + '</ul>' +
    '<ul class="list-disc pl-4 text-gray-500">' + items('persisted') + '</ul>' +
    '</div></div>';
}

/** 提交复查：服务端复跑审查并对比新旧 findings，状态流转到 rechecking */
export function recheckSession(sessionId: string): void {
  window.showToast?.('⏳ 复查中，请稍候…', 'info');
  collabApi('/collab/review-sessions/' + sessionId + '/recheck', { method: 'POST', body: JSON.stringify({}) }).then((d) => {
    if (d.status === 'success') {
      showReviewSessionDetail(sessionId);
      window.setTimeout(() => showRecheckResult(d), 400);
    } else {
      window.showToast?.(collabErrMsg(d), 'info');
    }
  });
}

/** 整改记录列表 + 登记表单 */
function buildRectificationSection(sessionId: string, rects: Array<Record<string, unknown>>): string {
  let list = '';
  if (!rects.length) {
    list = '<p class="text-sm text-gray-400 py-2">暂无整改记录</p>';
  } else {
    list = '<table class="collab-table"><tr><th>条款</th><th>实体</th><th>整改动作</th><th>责任人</th><th>状态</th><th>备注</th><th>操作</th></tr>';
    for (const rc of rects) {
      const done = rc.status === 'done';
      const badge = done
        ? '<span class="collab-badge collab-badge-approved">done</span>'
        : '<span class="collab-badge collab-badge-pending">pending</span>';
      const act = done
        ? ''
        : '<button class="text-xs text-green-700 underline" onclick="markRectificationDone(\'' + String(rc.id) + '\', \'' + sessionId + '\')">标记完成</button>';
      list += '<tr><td>' + escHtml(String(rc.clause_id || '-')) + '</td><td>' + escHtml(String(rc.entity_id || '-')) + '</td><td>' + escHtml(String(rc.action || '')) + '</td><td>' + escHtml(String(rc.owner || '')) + '</td><td>' + badge + '</td><td>' + escHtml(String(rc.note || '')) + '</td><td>' + act + '</td></tr>';
    }
    list += '</table>';
  }
  const form =
    '<div class="mt-2"><div class="flex gap-2 flex-wrap mb-2">' +
    '<input id="rs-rect-clause" class="input text-sm w-24" placeholder="条款ID" />' +
    '<input id="rs-rect-entity" class="input text-sm w-28" placeholder="实体ID" />' +
    '<input id="rs-rect-action" class="input text-sm flex-1" placeholder="整改动作" />' +
    '<input id="rs-rect-owner" class="input text-sm w-28" placeholder="责任人ID" />' +
    '</div><div class="flex justify-end">' +
    '<button class="modal-btn modal-btn-primary text-xs" onclick="createRectification(\'' + sessionId + '\')">+ 登记整改项</button>' +
    '</div></div>';
  return '<div class="mb-4 border-t pt-3"><h4 class="font-medium mb-2">整改记录</h4>' + list + form + '</div>';
}

/** 登记整改项（单条） */
export function createRectification(sessionId: string): void {
  const val = (id: string) => ((document.getElementById(id) as HTMLInputElement | null)?.value?.trim() || '');
  const action = val('rs-rect-action');
  if (!action) {
    window.showToast?.('整改动作不能为空', 'info');
    return;
  }
  const item = { clause_id: val('rs-rect-clause'), entity_id: val('rs-rect-entity'), action, owner: val('rs-rect-owner') };
  collabApi('/collab/review-sessions/' + sessionId + '/rectifications', { method: 'POST', body: JSON.stringify({ items: [item] }) }).then((d) => {
    if (d.status === 'success') { showReviewSessionDetail(sessionId); } else { window.showToast?.(collabErrMsg(d), 'info'); }
  });
}

/** 标记整改完成 */
export function markRectificationDone(rid: string, sessionId: string): void {
  collabApi('/collab/rectifications/' + rid, { method: 'PUT', body: JSON.stringify({ status: 'done' }) }).then((d) => {
    if (d.status === 'success') { showReviewSessionDetail(sessionId); } else { window.showToast?.(collabErrMsg(d), 'info'); }
  });
}
