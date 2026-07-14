// ── 初始化 ──────────────────────────────────────────────
// ── 审查记录 ──────────────────────────────────────────────
function renderHistoryList() {
  const el = document.getElementById('history-list');
  if (!el) return;
  loadReviewResults();
  const search = (document.getElementById('history-search')?.value || '').toLowerCase();
  const filter = document.getElementById('history-filter')?.value || 'all';
  let filtered = reviewResults;
  if (filter === 'civil') filtered = filtered.filter(r => r.buildingType === 'civil');
  else if (filter === 'industrial') filtered = filtered.filter(r => r.buildingType === 'industrial');
  else if (filter === 'violations') filtered = filtered.filter(r => (r.details?.length || 0) > 0);
  else if (filter === 'clean') filtered = filtered.filter(r => (r.details?.length || 0) === 0);
  if (search) {
    filtered = filtered.filter(r =>
      r.drawingName.toLowerCase().includes(search) ||
      (r.details || []).some(v => (v.clause_id || '').toLowerCase().includes(search) || (v.clause_title || '').toLowerCase().includes(search))
    );
  }
  document.getElementById('history-total-count').textContent = filtered.length;
  if (filtered.length === 0) {
    el.innerHTML = '<div class="text-center text-gray-400 py-8">无匹配记录</div>';
    return;
  }
  el.innerHTML = filtered.map(r => {
    const viols = r.details?.length || 0;
    const btLabel = r.buildingType === 'civil' ? '民用' : r.buildingType === 'industrial' ? '工业' : '--';
    const criticalCount = (r.details || []).filter(v => v.severity === 'critical').length;
    const timeStr = new Date(r.reviewedAt).toLocaleString();
    const color = viols === 0 ? 'green' : criticalCount > 0 ? 'red' : 'orange';
    return '<div class="card p-3 cursor-pointer hover:shadow-md transition-shadow" onclick="viewHistoryDetail(\'' + r.id + '\')">' +
      '<div class="flex items-center justify-between">' +
      '<div class="flex items-center gap-3">' +
      '<span class="text-' + color + '-500 text-lg">' + (viols === 0 ? '✅' : criticalCount > 0 ? '🔴' : '🟡') + '</span>' +
      '<div><div class="font-medium text-sm">' + r.drawingName + '</div>' +
      '<div class="text-xs text-gray-400">' + btLabel + ' · ' + timeStr + '</div></div></div>' +
      '<div class="text-right"><div class="text-sm font-bold text-' + color + '-600">' + viols + ' 项</div>' +
      '<div class="text-xs text-gray-400">违规</div></div></div></div>';
  }).join('');
}
function viewHistoryDetail(id) {
  const r = reviewResults.find(x => x.id === id);
  if (!r) return;
  let modal = document.getElementById('history-detail-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'history-detail-modal';
    modal.className = 'fixed inset-0 bg-black bg-opacity-40 z-50 flex items-center justify-center';
    modal.onclick = function(e) { if (e.target === modal) closeHistoryModal(); };
    document.body.appendChild(modal);
  }
  modal.innerHTML = '<div class="bg-white rounded-xl shadow-2xl max-w-2xl w-full mx-4 max-h-[80vh] flex flex-col">' +
    '<div class="flex items-center justify-between p-4 border-b">' +
    '<h3 class="text-lg font-bold">审查详情: ' + r.drawingName + '</h3>' +
    '<button onclick="closeHistoryModal()" class="text-gray-400 hover:text-gray-600 text-xl">✕</button></div>' +
    '<div class="p-4 overflow-y-auto flex-1">' +
    '<div class="grid grid-cols-4 gap-3 mb-4">' +
    '<div class="card p-2 text-center"><div class="text-lg font-bold text-blue-600">' + (r.details?.length || 0) + '</div><div class="text-xs text-gray-400">违规</div></div>' +
    '<div class="card p-2 text-center"><div class="text-lg font-bold text-red-600">' + (r.details?.filter(v => v.severity === 'critical').length || 0) + '</div><div class="text-xs text-gray-400">严重</div></div>' +
    '<div class="card p-2 text-center"><div class="text-lg font-bold text-orange-600">' + (r.details?.filter(v => v.severity === 'major').length || 0) + '</div><div class="text-xs text-gray-400">主要</div></div>' +
    '<div class="card p-2 text-center"><div class="text-lg font-bold text-yellow-600">' + (r.details?.filter(v => v.severity !== 'critical' && v.severity !== 'major').length || 0) + '</div><div class="text-xs text-gray-400">轻微</div></div>' +
    '</div>' +
    '<div class="text-xs text-gray-400 mb-2">建筑类型: ' + (r.buildingType === 'civil' ? '民用' : '工业') + ' · 审查时间: ' + new Date(r.reviewedAt).toLocaleString() + '</div>' +
    '<div class="space-y-2">' +
    (r.details || []).slice(0, 50).map(v => {
      const sevColor = v.severity === 'critical' ? 'red' : v.severity === 'major' ? 'orange' : 'yellow';
      const sevLabel = v.severity === 'critical' ? '严重' : v.severity === 'major' ? '主要' : '轻微';
      return '<div class="p-2 bg-' + sevColor + '-50 rounded text-xs">' +
        '<div class="flex justify-between"><span class="font-medium">' + (v.clause_title || '') + '</span><span class="px-1.5 py-0.5 rounded bg-' + sevColor + '-100 text-' + sevColor + '-700">' + sevLabel + '</span></div>' +
        '<span class="text-gray-500">' + (v.clause_id || '') + ' · ' + (v.entity_type || '') + '</span><br/>' +
        '<span class="text-gray-400">' + (v.explanation || '') + '</span></div>';
    }).join('') + (r.details?.length > 50 ? '<div class="text-xs text-gray-400 text-center pt-2">... 仅显示前50项</div>' : '') +
    '</div></div></div>';
}
function closeHistoryModal() {
  const modal = document.getElementById('history-detail-modal');
  if (modal) modal.remove();
}
function clearReviewHistory() {
  if (!confirm('确定清空所有审查历史记录？此操作不可恢复。')) return;
  localStorage.removeItem('baa_review_results');
  reviewResults = [];
  renderHistoryList();
  loadDashboard();
}
document.addEventListener('DOMContentLoaded', () => {
  loadApiBase();  // 恢复API地址
  initAdminToken();  // 初始化密钥管理页专用管理令牌
  loadApiKeys();
  populateTokenSelect();
  loadParsedDrawings();
  renderDrawingList();
  refreshReviewDrawingSelect();
  loadReviewResults();
  loadDashboard();
  loadSpecs();

  // API地址变更时自动保存
  document.getElementById('api-base')?.addEventListener('change', saveApiBase);

  // 引擎状态
  try {
    const health = JSON.parse(document.getElementById('health-status').textContent || '{}');
    const specCount = SPEC_DATA.length;
    document.getElementById('engine-status').innerHTML =
      '<div class="flex justify-between"><span>原子函数</span><span>30/30 已注册</span></div>' +
      '<div class="flex justify-between"><span>规范库</span><span>' + specCount + '条 (10L1+10L2+11L3)</span></div>' +
      '<div class="flex justify-between"><span>建筑类型阈值</span><span>civil/industrial</span></div>' +
      '<div class="flex justify-between"><span>判定过滤</span><span>实体类型匹配 (90.8%)</span></div>';
  } catch(e) {
    document.getElementById('engine-status').innerHTML =
      '<div class="flex justify-between"><span>原子函数</span><span>30/30 已注册</span></div>' +
      '<div class="flex justify-between"><span>规范库</span><span>30条 (10L1+10L2+11L3)</span></div>' +
      '<div class="flex justify-between"><span>建筑类型阈值</span><span>civil/industrial</span></div>' +
      '<div class="flex justify-between"><span>判定过滤</span><span>实体类型匹配 (90.8%)</span></div>';
  }
});

// ── 预览缩放 ──────────────────────────────────────────────
function zoomImage(img) {
  if (!img || !img.src || img.style.display === 'none') return;
  let modal = document.getElementById('zoom-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'zoom-modal';
    modal.className = 'fixed inset-0 bg-black bg-opacity-80 z-50 flex items-center justify-center cursor-zoom-out';
    modal.onclick = function() { modal.remove(); };
    document.body.appendChild(modal);
  }
  modal.innerHTML = '<img src="' + img.src + '" class="max-w-[95vw] max-h-[95vh] object-contain" />';
}

// P43 collab frontend
var collabToken = localStorage.getItem('baa_collab_token') || '';
var collabUser = {};
try { collabUser = JSON.parse(localStorage.getItem('baa_collab_user') || '{}'); } catch(e) {}

function collabApi(path, options) {
  options = options || {};
  var url = API_BASE() + path;
  var headers = {'Content-Type': 'application/json'};
  if (collabToken) headers['Authorization'] = 'Bearer ' + collabToken;
  if (options.headers) { for (var k in options.headers) headers[k] = options.headers[k]; }
  options.headers = headers;
  return fetch(url, options).then(function(r) { return r.json(); });
}

function closeCollabModal() { var el = document.getElementById('collab-modal-overlay'); if (el) el.style.display = 'none'; }
function setModalBody(html) { var el = document.getElementById('collab-modal-body'); if (el) { el.innerHTML = html; document.getElementById('collab-modal-overlay').style.display = 'flex'; } }

function showCollabLogin() {
  document.getElementById('collab-login-form').style.display = 'block';
  document.getElementById('collab-register-form').style.display = 'none';
  var btns = document.querySelectorAll('#collab-auth-tabs button');
  btns[0].className = 'flex-1 px-4 py-2 rounded text-sm font-medium bg-blue-500 text-white';
  btns[1].className = 'flex-1 px-4 py-2 rounded text-sm font-medium bg-gray-100 text-gray-600';
}

function showCollabRegister() {
  document.getElementById('collab-login-form').style.display = 'none';
  document.getElementById('collab-register-form').style.display = 'block';
  var btns = document.querySelectorAll('#collab-auth-tabs button');
  btns[0].className = 'flex-1 px-4 py-2 rounded text-sm font-medium bg-gray-100 text-gray-600';
  btns[1].className = 'flex-1 px-4 py-2 rounded text-sm font-medium bg-blue-500 text-white';
}

function collabLogin() {
  var u = document.getElementById('collab-username').value.trim();
  var p = document.getElementById('collab-password').value;
  if (!u || !p) { document.getElementById('collab-auth-msg').textContent = '请输入用户名和密码'; return; }
  collabApi('/collab/auth/login', { method: 'POST', body: JSON.stringify({username: u, password: p}) }).then(function(d) {
    if (d.status === 'success') {
      collabToken = d.token; collabUser = d.user;
      localStorage.setItem('baa_collab_token', collabToken);
      localStorage.setItem('baa_collab_user', JSON.stringify(collabUser));
      document.getElementById('collab-auth-msg').textContent = '';
      collabEnterMain();
    } else { document.getElementById('collab-auth-msg').textContent = d.detail || '登录失败'; }
  });
}

function collabRegister() {
  var u = document.getElementById('collab-reg-username').value.trim();
  var p = document.getElementById('collab-reg-password').value;
  var e = document.getElementById('collab-reg-email').value.trim();
  var dn = document.getElementById('collab-reg-name').value.trim();
  if (!u || !p) { document.getElementById('collab-reg-msg').textContent = '用户名和密码不能为空'; return; }
  if (p.length < 6) { document.getElementById('collab-reg-msg').textContent = '密码至少6位'; return; }
  var body = {username: u, password: p};
  if (e) { body.email = e; body.display_name = dn; }
  collabApi('/collab/auth/register', { method: 'POST', body: JSON.stringify(body) }).then(function(d) {
    if (d.status === 'success') {
      document.getElementById('collab-reg-msg').textContent = '注册成功，请登录';
      document.getElementById('collab-reg-msg').style.color = '#059669';
      showCollabLogin();
      document.getElementById('collab-username').value = u;
    } else { document.getElementById('collab-reg-msg').textContent = d.detail || '注册失败'; }
  });
}

function collabLogout() {
  collabToken = ''; collabUser = {};
  localStorage.removeItem('baa_collab_token');
  localStorage.removeItem('baa_collab_user');
  document.getElementById('collab-main-section').style.display = 'none';
  document.getElementById('collab-login-section').style.display = 'block';
}

function collabEnterMain() {
  document.getElementById('collab-login-section').style.display = 'none';
  document.getElementById('collab-main-section').style.display = 'block';
  document.getElementById('collab-user-display').textContent = '👤 ' + (collabUser.display_name || collabUser.username);
  collabRefresh();
}

function collabRefresh() { loadCollabStats(); loadCollabTeams(); }

function loadCollabStats() {
  collabApi('/collab/stats').then(function(d) {
    if (d.status === 'success') {
      document.getElementById('cs-users').textContent = d.stats.users;
      document.getElementById('cs-teams').textContent = d.stats.teams;
      document.getElementById('cs-projects').textContent = d.stats.active_projects;
      document.getElementById('cs-sessions').textContent = d.stats.review_sessions;
    }
  });
}

function loadCollabTeams() {
  collabApi('/collab/teams').then(function(d) {
    var el = document.getElementById('collab-teams');
    if (d.status !== 'success') { el.innerHTML = '\u52a0\u8f7d\u5931\u8d25'; return; }
    if (!d.teams.length) { el.innerHTML = '\u6682\u65e0\u56e2\u961f'; return; }
    var h = '<table class="collab-table"><tr><th>\u540d\u79f0</th><th>\u6210\u5458</th><th>\u89d2\u8272</th><th>\u65f6\u95f4</th><th>\u64cd\u4f5c</th></tr>';
    for (var i = 0; i < d.teams.length; i++) {
      var t = d.teams[i];
      h += '<tr><td><strong>' + t.name + '</strong></td><td>' + t.member_count + '</td><td><span class="collab-badge collab-badge-' + t.my_role + '">' + t.my_role + '</span></td><td>' + new Date(t.created_at*1000).toLocaleDateString() + '</td><td><button class="text-blue-600 text-xs underline" onclick="showTeamDetail(&#39;' + t.id + '&#39;)">📋</button></td></tr>';
    }
    h += '</table>';
    el.innerHTML = h;
  });
}

function showCreateTeamModal() {
  setModalBody('<h3 class="text-lg font-bold mb-4">\u65b0\u5efa\u56e2\u961f</h3><input id="modal-team-name" class="input w-full mb-2" placeholder="\u56e2\u961f\u540d\u79f0" /><textarea id="modal-team-desc" class="input w-full mb-3" placeholder="\u63cf\u8ff0" rows="2"></textarea><div class="flex gap-2 justify-end"><button class="modal-btn modal-btn-secondary" onclick="closeCollabModal()">\u53d6\u6d88</button><button class="modal-btn modal-btn-primary" onclick="createTeam()">\u521b\u5efa</button></div>');
}

function createTeam() {
  var name = document.getElementById('modal-team-name').value.trim();
  if (!name) return;
  var desc = document.getElementById('modal-team-desc').value.trim();
  collabApi('/collab/teams', { method: 'POST', body: JSON.stringify({name: name, description: desc}) }).then(function(d) {
    if (d.status === 'success') { closeCollabModal(); collabRefresh(); } else { alert(d.detail || '\u521b\u5efa\u5931\u8d25'); }
  });
}

function showTeamDetail(teamId) {
  Promise.all([collabApi('/collab/teams/' + teamId), collabApi('/collab/teams/' + teamId + '/projects')]).then(function(r) {
    if (r[0].status !== 'success') return;
    var team = r[0].team, projects = r[1].projects || [];
    var mh = '<table class="collab-table"><tr><th>\u7528\u6237</th><th>\u89d2\u8272</th><th>\u65f6\u95f4</th></tr>';
    for (var i = 0; i < team.members.length; i++) {
      var m = team.members[i];
      mh += '<tr><td>' + (m.display_name || m.username) + '</td><td><span class="collab-badge collab-badge-' + m.role + '">' + m.role + '</span></td><td>' + new Date(m.joined_at*1000).toLocaleDateString() + '</td></tr>';
    }
    mh += '</table>';
    var ph = '';
    if (projects.length === 0) { ph = '<p class="text-sm text-gray-400 py-2">\u6682\u65e0\u9879\u76ee</p>'; } else {
      ph = '<table class="collab-table"><tr><th>\u9879\u76ee</th><th>\u56fe\u7eb8</th><th>\u5ba1\u67e5</th><th>\u72b6\u6001</th><th>\u64cd\u4f5c</th></tr>';
      for (var i = 0; i < projects.length; i++) {
        var p = projects[i];
        ph += '<tr><td><strong>' + p.name + '</strong></td><td>' + p.file_count + '</td><td>' + p.review_count + '</td><td>' + p.status + '</td><td><button class="text-blue-600 text-xs underline" onclick="showProjectDetail(&#39;' + p.id + '&#39;)">📝</button></td></tr>';
      }
      ph += '</table>';
    }
    setModalBody('<h3 class="text-lg font-bold mb-4">\u56e2\u961f: ' + team.name + '</h3><div class="mb-4"><h4 class="font-medium mb-2">\u6210\u5458 (' + team.members.length + ')</h4>' + mh + '</div><div><div class="flex justify-between items-center mb-2"><h4 class="font-medium">\u9879\u76ee</h4><button class="modal-btn modal-btn-primary text-xs" onclick="showCreateProjectModal(&#39;' + teamId + '&#39;)">+ \u65b0\u5efa\u9879\u76ee</button></div>' + ph + '</div><div class="flex gap-2 justify-end mt-4"><button class="modal-btn modal-btn-secondary" onclick="closeCollabModal()">\u5173\u95ed</button></div>');
  });
}

function showCreateProjectModal(teamId) {
  setModalBody('<h3 class="text-lg font-bold mb-4">\u65b0\u5efa\u9879\u76ee</h3><input id="modal-proj-name" class="input w-full mb-2" placeholder="\u9879\u76ee\u540d\u79f0" /><textarea id="modal-proj-desc" class="input w-full mb-2" placeholder="\u63cf\u8ff0" rows="2"></textarea><input id="modal-proj-type" class="input w-full mb-2" placeholder="\u5efa\u7b51\u7c7b\u578b" /><div class="flex gap-2 justify-end"><button class="modal-btn modal-btn-secondary" onclick="showTeamDetail(&#39;' + teamId + '&#39;)">\u8fd4\u56de</button><button class="modal-btn modal-btn-primary" onclick="createProject(&#39;' + teamId + '&#39;)">\u521b\u5efa</button></div>');
}

function createProject(teamId) {
  var name = document.getElementById('modal-proj-name').value.trim();
  if (!name) return;
  var desc = document.getElementById('modal-proj-desc').value.trim();
  var btype = document.getElementById('modal-proj-type').value.trim();
  collabApi('/collab/projects', { method: 'POST', body: JSON.stringify({name: name, team_id: teamId, description: desc, building_type: btype}) }).then(function(d) {
    if (d.status === 'success') { showTeamDetail(teamId); } else { alert(d.detail || '\u521b\u5efa\u5931\u8d25'); }
  });
}

function showProjectDetail(projectId) {
  Promise.all([collabApi('/collab/projects/' + projectId), collabApi('/collab/projects/' + projectId + '/review-sessions')]).then(function(r) {
    if (r[0].status !== 'success') return;
    var proj = r[0].project, sessions = r[1].review_sessions || [];
    var mh = '<table class="collab-table"><tr><th>\u7528\u6237</th><th>\u6743\u9650</th></tr>';
    for (var i = 0; i < proj.members.length; i++) {
      var m = proj.members[i];
      mh += '<tr><td>' + (m.display_name || m.username) + '</td><td><span class="collab-badge">' + m.permission + '</span></td></tr>';
    }
    mh += '</table>';
    var sh = '';
    if (sessions.length === 0) { sh = '<p class="text-sm text-gray-400 py-2">\u6682\u65e0\u5ba1\u67e5\u4f1a\u8bdd</p>'; } else {
      sh = '<table class="collab-table"><tr><th>\u540d\u79f0</th><th>\u72b6\u6001</th><th>\u521b\u5efa\u4eba</th><th>\u65f6\u95f4</th><th>\u64cd\u4f5c</th></tr>';
      for (var i = 0; i < sessions.length; i++) {
        var s = sessions[i];
        sh += '<tr><td>' + s.name + '</td><td><span class="collab-badge collab-badge-' + s.status + '">' + s.status + '</span></td><td>' + (s.creator_name || '') + '</td><td>' + new Date(s.created_at*1000).toLocaleString() + '</td><td><button class="text-blue-600 text-xs underline" onclick="showReviewSessionDetail(&#39;' + s.id + '&#39;)">📝</button></td></tr>';
      }
      sh += '</table>';
    }
    setModalBody('<h3 class="text-lg font-bold mb-4">\u9879\u76ee: ' + proj.name + '</h3><div class="mb-4"><h4 class="font-medium mb-2">\u6210\u5458</h4>' + mh + '</div><div><div class="flex justify-between items-center mb-2"><h4 class="font-medium">\u5ba1\u67e5\u4f1a\u8bdd</h4><button class="modal-btn modal-btn-primary text-xs" onclick="showCreateReviewSessionModal(&#39;' + projectId + '&#39;)">+ \u65b0\u5efa\u5ba1\u67e5</button></div>' + sh + '</div><div class="flex gap-2 justify-end mt-4"><button class="modal-btn modal-btn-secondary" onclick="closeCollabModal()">\u5173\u95ed</button></div>');
  });
}

function showCreateReviewSessionModal(projectId) {
  setModalBody('<h3 class="text-lg font-bold mb-4">\u65b0\u5efa\u5ba1\u67e5\u4f1a\u8bdd</h3><input id="modal-rs-name" class="input w-full mb-2" placeholder="\u540d\u79f0" /><textarea id="modal-rs-desc" class="input w-full mb-2" placeholder="\u63cf\u8ff0" rows="2"></textarea><div class="flex gap-2 justify-end"><button class="modal-btn modal-btn-secondary" onclick="showProjectDetail(&#39;' + projectId + '&#39;)">\u8fd4\u56de</button><button class="modal-btn modal-btn-primary" onclick="createReviewSession(&#39;' + projectId + '&#39;)">\u521b\u5efa</button></div>');
}

function createReviewSession(projectId) {
  var name = document.getElementById('modal-rs-name').value.trim();
  if (!name) return;
  var desc = document.getElementById('modal-rs-desc').value.trim();
  collabApi('/collab/review-sessions', { method: 'POST', body: JSON.stringify({project_id: projectId, name: name, description: desc}) }).then(function(d) {
    if (d.status === 'success') { showProjectDetail(projectId); } else { alert(d.detail || '\u521b\u5efa\u5931\u8d25'); }
  });
}

function showReviewSessionDetail(sessionId) {
  Promise.all([
    collabApi('/collab/review-sessions/' + sessionId),
    collabApi('/collab/review-sessions/' + sessionId + '/comments'),
    collabApi('/collab/review-sessions/' + sessionId + '/approval-flow')
  ]).then(function(r) {
    if (r[0].status !== 'success') return;
    var rs = r[0].review_session, comments = r[1].comments || [], flow = r[2].approval_flow;
    var statusBadge = '<span class="collab-badge collab-badge-' + rs.status + '">' + rs.status + '</span>';
    var ch = '';
    if (comments.length === 0) { ch = '<p class="text-sm text-gray-400 py-2">\u6682\u65e0\u8bc4\u8bba</p>'; } else {
      for (var i = 0; i < comments.length; i++) {
        var c = comments[i];
        var icon = c.comment_type === 'issue' ? '\u26a0\ufe0f' : c.comment_type === 'suggestion' ? '\U0001f4a1' : c.comment_type === 'question' ? '\u2753' : '\u2705';
        ch += '<div class="comment-box comment-' + c.comment_type + '"><div class="flex justify-between items-start"><span class="font-medium text-sm">' + icon + ' ' + (c.author_name || '') + '</span><span class="text-xs text-gray-400">' + new Date(c.created_at*1000).toLocaleString() + '</span></div><p class="text-sm mt-1">' + c.content + '</p>';
        if (c.clause_ref) { ch += '<div class="text-xs text-gray-400 mt-1">\u2022 \u6761\u6b3e: ' + c.clause_ref + '</div>'; }
        if (c.entity_ref) { ch += '<div class="text-xs text-gray-400">\u2022 \u5b9e\u4f53: ' + c.entity_ref + '</div>'; }
        ch += '</div>';
      }
    }
    var fh = '';
    if (flow) {
      fh = '<table class="collab-table"><tr><th>\u5e8f\u53f7</th><th>\u5ba1\u6279\u4eba</th><th>\u72b6\u6001</th><th>\u610f\u89c1</th><th>\u65f6\u95f4</th></tr>';
      for (var i = 0; i < flow.steps.length; i++) {
        var st = flow.steps[i];
        var sb = '<span class="collab-badge collab-badge-' + st.status + '">' + st.status + '</span>';
        fh += '<tr><td>' + st.order + '</td><td>' + (st.reviewer_name || '') + '</td><td>' + sb + '</td><td>' + (st.comment || '') + '</td><td>' + (st.acted_at ? new Date(st.acted_at*1000).toLocaleString() : '') + '</td></tr>';
      }
      fh += '</table>';
    } else {
      fh = '<p class="text-sm text-gray-400 py-2">\u6682\u65e0\u5ba1\u6279\u6d41\u7a0b</p>';
    }
    setModalBody('<h3 class="text-lg font-bold mb-4">\u5ba1\u67e5\u4f1a\u8bdd: ' + rs.name + ' ' + statusBadge + '</h3><div class="mb-4"><h4 class="font-medium mb-2">\u8bc4\u8bba</h4>' + ch + '</div><div><h4 class="font-medium mb-2">\u5ba1\u6279\u6d41\u7a0b</h4>' + fh + '</div><div class="flex gap-2 justify-end mt-4"><button class="modal-btn modal-btn-secondary" onclick="closeCollabModal()">\u5173\u95ed</button></div>');
  });
}

// Auto-login if token exists
if (collabToken) {
  setTimeout(function() {
    var page = document.getElementById('page-collab');
    if (page && page.classList.contains('active')) {
      collabEnterMain();
    }
  }, 500);
}

</script>
