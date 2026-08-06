// ── 全局状态 ──────────────────────────────────────────────
// 规范库数据（从后端 API 动态加载）
let SPEC_DATA = [];

// 从 localStorage 恢复API地址
function loadApiBase() {
  const saved = localStorage.getItem('baa_api_base');
  const input = document.getElementById('api-base');
  if (saved && input) input.value = saved;
}

function saveApiBase() {
  const input = document.getElementById('api-base');
  if (input) localStorage.setItem('baa_api_base', input.value);
}

const API_BASE = () => document.getElementById('api-base')?.value || 'http://localhost:8000';
const HEADERS = () => {
  const key = getActiveKeyValue();
  return key ? {'Authorization': 'Bearer ' + key} : {};
};
let reviewHistory = [];

// ── 访问令牌管理（连接配置页用） ───────────────────
let apiKeys = [];
let activeKey = '';
function getApiKey() {
  if (!activeKey) return '';
  const k = apiKeys.find(k => k.id === activeKey);
  return k ? k.key : '';
}


function loadApiKeys() {
  try {
    const stored = localStorage.getItem('baa_api_keys');
    apiKeys = stored ? JSON.parse(stored) : [];
    activeKey = localStorage.getItem('baa_active_key') || '';
  } catch (e) {
    apiKeys = [];
    activeKey = '';
  }
  populateTokenSelect();
}

function saveApiKeys() {
  localStorage.setItem('baa_api_keys', JSON.stringify(apiKeys));
}

function maskKey(key) {
  if (key.length <= 8) return key;
  return key.slice(0, 4) + '...' + key.slice(-4);
}

/* ── Toast 通知系统 ──
 * 替代 window.alert，提供轻量级右下角通知。
 * 自动 4s 后消失，最多同时 5 个。
 */
function showToast(message, type = 'info', duration = 4000) {
  if (typeof message !== 'string' || !message) return;
  const icons = { info: 'ℹ️', success: '✅', error: '❌', warn: '⚠️' };
  const container = (() => {
    let c = document.getElementById('toast-container');
    if (!c) {
      c = document.createElement('div');
      c.id = 'toast-container';
      c.className = 'toast-container';
      document.body.appendChild(c);
    }
    return c;
  })();
  const toast = document.createElement('div');
  toast.className = 'toast toast-' + type;
  toast.innerHTML = '<span>' + (icons[type] || 'ℹ️') + '</span><span>' + message + '</span>';
  container.appendChild(toast);
  if (container.children.length > 5) container.firstChild.remove();
  setTimeout(() => { toast.style.opacity = '0'; toast.style.transform = 'translateX(20px)'; }, duration);
  setTimeout(() => { if (toast.parentNode) toast.parentNode.removeChild(toast); }, duration + 300);
}

/* ── 审查进度条 ──
 * 渲染为 <div class="review-progress"> 结构，替换纯文本 "⏳ 正在审查"
 */
function renderProgress(el, label, pct) {
  if (!el) return;
  el.className = 'review-progress';
  el.innerHTML =
    '<div class="review-progress-text"><span>' + (label || '处理中') + '</span><span>' + (pct || 0) + '%</span></div>' +
    '<div class="review-progress-bar"><div class="review-progress-fill" style="width:' + (pct || 0) + '%"></div></div>';
}

function getActiveKeyValue() {
  const k = apiKeys.find(k => k.id === activeKey);
  return k ? k.key : '';
}

function switchApiKey(id) {
  activeKey = id;
  localStorage.setItem('baa_active_key', activeKey);
  populateTokenSelect();
}

function deleteCurrentApiKey() {
  if (!activeKey) { showToast('当前没有选中任何令牌', 'info'); return; }
  if (!confirm('确认删除当前令牌？')) return;
  deleteApiKey(activeKey);
}

function populateTokenSelect() {
  const select = document.getElementById('active-key-select');
  const hint = document.getElementById('token-hint');
  if (!select) return;
  
  select.innerHTML = '<option value="">无令牌（开发模式）</option>';
  
  apiKeys.forEach(k => {
    const isActive = k.id === activeKey;
    const opt = document.createElement('option');
    opt.value = k.id;
    opt.textContent = k.name + ' (' + maskKey(k.key) + ')';
    if (isActive) opt.selected = true;
    select.appendChild(opt);
  });
  
  if (hint) {
    hint.textContent = apiKeys.length > 0
      ? '共 ' + apiKeys.length + ' 个本地令牌。外部项目的token可手动添加。'
      : '暂无令牌。可在「密钥管理」页面创建后在此添加，或点击下方手动输入。';
  }
}

// 手动添加外部令牌（用于对接外部项目如EMA2的token）
function addApiKey() {
  const name = prompt('令牌名称（如：EMA2对接）');
  if (!name) return;
  const key = prompt('请输入令牌内容（从密钥管理页面复制）');
  if (!key) return;
  apiKeys.push({id: 'key_' + Date.now(), name, key, created: Date.now()});
  saveApiKeys();
  activeKey = apiKeys[apiKeys.length - 1].id;
  localStorage.setItem('baa_active_key', activeKey);
  populateTokenSelect();
}

function deleteApiKey(id) {
  if (!confirm('确认删除此本地令牌？')) return;
  apiKeys = apiKeys.filter(k => k.id !== id);
  if (activeKey === id) {
    activeKey = apiKeys.length > 0 ? apiKeys[apiKeys.length - 1].id : '';
    localStorage.setItem('baa_active_key', activeKey);
  }
  saveApiKeys();
  populateTokenSelect();
}

function copyApiKey(id) {
  const k = apiKeys.find(k => k.id === id);
  if (!k) return;
  navigator.clipboard.writeText(k.key).then(() => {
    showToast('令牌已复制到剪贴板', 'info');
  }).catch(() => {
    showToast('复制失败，请手动复制', 'error');
  });
}

async function refreshTokenSelect() {
  const btn = document.querySelector('#active-key-select + button');
  if (btn) btn.textContent = '⏳';
  const hint = document.getElementById('token-hint');
  if (hint) hint.textContent = '正在从服务端刷新密钥列表...';
  try {
    const data = await apiGet('/admin/keys');
    if (data && data.data && data.data.length > 0) {
      if (hint) {
        hint.textContent = '✅ 服务端有 ' + data.data.length + ' 个已管理密钥。点击「📥 从密钥管理导入」选择并填入。';
      }
    } else {
      if (hint) hint.textContent = '服务端暂无可用密钥，请先在「密钥管理」页面创建。';
    }
  } catch (e) {
    if (hint) hint.textContent = '❌ 刷新失败: ' + e.message + '（请确认当前令牌有admin权限）';
  } finally {
    if (btn) btn.textContent = '🔄';
  }
}

let _importingKeyId = null;

async function importServerKey() {
  // 先检查当前令牌是否有效
  const activeKeyVal = getActiveKeyValue();
  if (!activeKeyVal) {
    if (!confirm('当前未选择任何令牌，后端 /admin/keys 需要admin权限。\n是否仍要尝试？（建议先在「密钥管理」创建admin密钥后选择）')) {
      return;
    }
  }

  const list = document.getElementById('import-key-list');
  if (!list) { showToast('页面元素异常', 'info'); return; }
  list.innerHTML = '<div class="text-center text-gray-400 text-sm py-4">⏳ 加载中...</div>';
  document.getElementById('import-key-modal').classList.remove('hidden');
  
  try {
    const data = await apiGet('/admin/keys');
    if (!data || !data.data || data.data.length === 0) {
      list.innerHTML = '<div class="text-center text-gray-400 text-sm py-4">暂无可用密钥，请先在「密钥管理」页面创建。</div>';
      return;
    }
    
    // 检查是否返回了403错误
    if (data.detail && data.detail.error_code === 'FORBIDDEN') {
      list.innerHTML = '<div class="text-center text-red-500 text-sm py-4">❌ 权限不足：当前令牌无admin权限。\n请先在「密钥管理」页面创建admin密钥，\n然后在连接配置页选择该令牌后再试。</div>';
      return;
    }

    list.innerHTML = '';
    data.data.forEach(k => {
      if (!k.enabled) return;
      const div = document.createElement('div');
      const label = k.label || k.key_id;
      const expires = k.expires_at ? '过期: ' + formatDate(k.expires_at) : '永不过期';
      div.className = 'flex items-center justify-between p-3 border rounded-lg hover:bg-gray-50 cursor-pointer';
      div.innerHTML =
        '<div class="flex-1 min-w-0">' +
          '<div class="font-medium text-sm">' + label + '</div>' +
          '<div class="text-xs text-gray-400">权限: ' + k.permission + ' | ' + expires + '</div>' +
        '</div>' +
        '<button onclick="importSelectedKey(\'' + k.key_id + '\')" class="px-3 py-1.5 bg-purple-600 text-white rounded text-xs hover:bg-purple-700 shrink-0">选择并填入</button>';
      list.appendChild(div);
    });
  } catch (e) {
    list.innerHTML = '<div class="text-center text-red-500 text-sm py-4">❌ 加载失败: ' + e.message + '</div>';
  }
}

async function importSelectedKey(keyId) {
  _importingKeyId = keyId;
  const keyValue = prompt('请输入此密钥的原始值（从密钥管理页创建时复制）：');
  if (!keyValue) return;

  // 后端验证：确认密钥有效
  const btn = event?.target || document.querySelector('#import-key-modal button');
  if (btn) { btn.textContent = '验证中...'; btn.disabled = true; }

  try {
    const verifyResult = await apiPostJSON('/admin/keys/verify', { raw_key: keyValue });
    if (verifyResult.status === 'success' && verifyResult.valid) {
      const keyInfo = verifyResult.key_info || {};
      const label = (keyInfo.label || keyInfo.key_id || keyId) + ' (imported)';
      apiKeys.push({id: 'key_' + Date.now(), name: label, key: keyValue, created: Date.now()});
      saveApiKeys();
      activeKey = apiKeys[apiKeys.length - 1].id;
      localStorage.setItem('baa_active_key', activeKey);
      populateTokenSelect();
      closeImportKeyModal();
      showToast('✅ 密钥验证通过，已添加到本地令牌列表', 'success');
    } else {
      showToast('❌ 密钥验证失败：' + (verifyResult.message || '密钥无效或已过期'), 'error');
    }
  } catch (e) {
    // 后端验证不可用时，回退到直接保存
    if (confirm('无法验证密钥有效性（' + e.message + '）。是否仍要保存到本地？')) {
      apiKeys.push({id: 'key_' + Date.now(), name: keyId + ' (imported)', key: keyValue, created: Date.now()});
      saveApiKeys();
      activeKey = apiKeys[apiKeys.length - 1].id;
      localStorage.setItem('baa_active_key', activeKey);
      populateTokenSelect();
      closeImportKeyModal();
    }
  } finally {
    if (btn) { btn.textContent = '选择并填入'; btn.disabled = false; }
  }
}

function closeImportKeyModal() {
  document.getElementById('import-key-modal').classList.add('hidden');
}


// ── 密钥管理（后端 /admin/keys 对接） ─────────────────

let _selectedDetailKeyId = null;

// ── 密钥管理页专用管理令牌（独立于连接配置页的 localStorage） ──
let _adminToken = '';

async function initAdminToken() {
  // 开发模式: /admin/bootstrap-key 返回空字符串，此时后端不校验
  // 生产模式: 获取环境变量中的 admin key
  try {
    const data = await fetch(API_BASE() + '/admin/bootstrap-key').then(r => r.json());
    if (data.status === 'success') {
      _adminToken = data.admin_key || '';
    }
  } catch (e) {
    _adminToken = '';
  }
}

function adminHeaders(method) {
  const h = {};
  if (_adminToken) {
    h['Authorization'] = 'Bearer ' + _adminToken;
  }
  // 只有 POST/PUT 才加 Content-Type（GET 加 Content-Type 会触发不必要的 OPTIONS preflight）
  if (method && method !== 'GET') {
    h['Content-Type'] = 'application/json';
  }
  return h;
}

async function adminGet(path) {
  const r = await fetch(API_BASE() + path, {method: 'GET', headers: adminHeaders('GET')});
  return r.json();
}

async function adminPost(path, body) {
  const r = await fetch(API_BASE() + path, {
    method: 'POST',
    headers: adminHeaders('POST'),
    body: JSON.stringify(body)
  });
  return r.json();
}

async function adminPost(path, body) {
  const r = await fetch(API_BASE() + path, {
    method: 'POST',
    headers: adminHeaders('POST'),
    body: JSON.stringify(body)
  });
  return r.json();
}

async function adminDelete(path) {
  const r = await fetch(API_BASE() + path, {
    method: 'DELETE',
    headers: adminHeaders('DELETE'),
  });
  return r.json();
}

async function apiPostJSON(path, body) {
  const r = await fetch(API_BASE() + path, {
    method: 'POST',
    headers: {...HEADERS(), 'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  });
  return r.json();
}

function formatDate(iso) {
  if (!iso) return '-';
  const d = new Date(iso);
  return d.toLocaleString('zh-CN', {year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit'});
}

function permissionBadge(perm) {
  const colors = {admin:'bg-red-100 text-red-800', write:'bg-blue-100 text-blue-800', read:'bg-green-100 text-green-800', limited:'bg-gray-100 text-gray-800'};
  const c = colors[perm] || 'bg-gray-100';
  return '<span class="inline-block px-2 py-0.5 rounded text-xs font-medium ' + c + '">' + perm + '</span>';
}

function enabledBadge(enabled) {
  return enabled
    ? '<span class="inline-block px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700">✓ 启用</span>'
    : '<span class="inline-block px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700">✗ 已禁用</span>';
}

async function loadAdminKeys() {
  const table = document.getElementById('admin-keys-table');
  const authHint = document.getElementById('admin-key-auth-hint');
  if (!table) return;
  table.innerHTML = '<div class="text-center py-8 text-gray-400 text-sm">加载中...</div>';
  if (authHint) authHint.innerHTML = '';

  // 检查当前令牌是否有效
  const activeKeyVal = getActiveKeyValue();
  if (!activeKeyVal) {
    if (authHint) {
      authHint.innerHTML = '<div class="px-3 py-2 bg-yellow-50 border border-yellow-200 rounded text-yellow-700">⚠️ 当前未选择访问令牌，密钥管理操作需要admin权限。请先前往 <a href="#" onclick="document.querySelector(\'[data-page=settings]\').click();return false" class="text-blue-600 underline">🔌 连接配置</a> 选择一个admin令牌。</div>';
    }
  }

  try {
    const showDisabled = document.getElementById('show-disabled')?.checked;
    const data = await adminGet('/admin/keys?include_disabled=' + (showDisabled ? 'true' : 'false'));
    const statsData = await adminGet('/admin/keys/stats');

    // 更新统计
    if (statsData && statsData.data) {
      document.getElementById('stat-total').textContent = statsData.data.summary.total;
      document.getElementById('stat-active').textContent = statsData.data.summary.active;
      document.getElementById('stat-disabled').textContent = statsData.data.summary.disabled;
      document.getElementById('stat-calls').textContent = statsData.data.summary.total_calls;
    }

    if (!data || !data.data || data.data.length === 0) {
      table.innerHTML = '<div class="text-center py-8 text-gray-400 text-sm">暂无密钥，点击「+ 创建密钥」开始</div>';
      return;
    }

    let html = '<table class="w-full text-sm"><thead><tr class="text-left text-gray-500 border-b">' +
      '<th class="pb-2 pr-3">标签</th>' +
      '<th class="pb-2 pr-3">权限</th>' +
      '<th class="pb-2 pr-3">状态</th>' +
      '<th class="pb-2 pr-3">创建时间</th>' +
      '<th class="pb-2 pr-3">过期时间</th>' +
      '<th class="pb-2 pr-3">调用次数</th>' +
      '<th class="pb-2">操作</th>' +
      '</tr></thead><tbody>';

    data.data.forEach(k => {
      const usage = k.usage || {};
      html += '<tr class="border-b hover:bg-gray-50">' +
        '<td class="py-2 pr-3 font-medium">' + (k.label || '-') + '</td>' +
        '<td class="py-2 pr-3">' + permissionBadge(k.permission) + '</td>' +
        '<td class="py-2 pr-3">' + enabledBadge(k.enabled) + '</td>' +
        '<td class="py-2 pr-3 text-gray-500">' + formatDate(k.created_at) + '</td>' +
        '<td class="py-2 pr-3 text-gray-500">' + formatDate(k.expires_at) + '</td>' +
        '<td class="py-2 pr-3 text-gray-500">' + (usage.total_calls || 0) + '</td>' +
        '<td class="py-2">' +
          '<button onclick="showKeyDetail(\'' + k.key_id + '\')" class="px-2 py-1 bg-gray-200 rounded text-xs hover:bg-gray-300 mr-1">详情</button>' +
          (k.has_raw_key ? '<button onclick="copyKeyFromDetail(\'' + k.key_id + '\')" class="px-2 py-1 bg-blue-100 rounded text-xs hover:bg-blue-200 mr-1">📋复制密钥</button>' : '') +
          (k.enabled ? '<button onclick="confirmRevokeKey(\'' + k.key_id + '\')" class="px-2 py-1 bg-red-100 rounded text-xs hover:bg-red-200 mr-1">撤销</button>' : '') +
          '<button onclick="confirmDeleteKey(\'' + k.key_id + '\')" class="px-2 py-1 bg-red-200 rounded text-xs hover:bg-red-300" title="永久删除（不可恢复）">🗑️</button>' +
        '</td>' +
        '</tr>';
    });

    html += '</tbody></table>';
    table.innerHTML = html;
  } catch (e) {
    const isAuthError = e.message && (e.message.includes('403') || e.message.includes('FORBIDDEN') || e.message.includes('Unauthorized'));
    if (authHint && isAuthError) {
      authHint.innerHTML = '<div class="px-3 py-2 bg-red-50 border border-red-200 rounded text-red-700">❌ 权限不足：当前令牌无admin权限。请前往 <a href="#" onclick="document.querySelector(\'[data-page=settings]\').click();return false" class="text-blue-600 underline">🔌 连接配置</a> 选择一个admin令牌或使用环境变量key。</div>';
    }
    table.innerHTML = '<div class="text-center py-8 text-red-500 text-sm">❌ 加载失败: ' + e.message + '</div>';
  }
}

function openCreateKeyModal() {
  document.getElementById('create-key-modal').classList.remove('hidden');
  document.getElementById('new-key-label').value = '';
  document.getElementById('new-key-permission').value = 'write';
  document.getElementById('new-key-ttl').value = '90';
}

function closeCreateKeyModal() {
  document.getElementById('create-key-modal').classList.add('hidden');
}

async function createAdminKey() {
  const label = document.getElementById('new-key-label').value.trim() || 'unnamed';
  const permission = document.getElementById('new-key-permission').value;
  const ttl = parseInt(document.getElementById('new-key-ttl').value);

  const btn = document.querySelector('#create-key-modal .bg-green-600');
  btn.textContent = '创建中...';
  btn.disabled = true;

  try {
    const data = await adminPost('/admin/keys', {label, permission, ttl_days: ttl});
    if (data.status === 'success' && data.data) {
      closeCreateKeyModal();
      // 显示创建成功modal
      document.getElementById('created-raw-key').textContent = data.data.raw_key;
      document.getElementById('created-key-info').innerHTML =
        '密钥ID: ' + data.data.key_id + '<br>' +
        '权限: ' + data.data.info.permission + '<br>' +
        '过期: ' + formatDate(data.data.info.expires_at);
      document.getElementById('key-created-modal').classList.remove('hidden');
      loadAdminKeys();
    } else {
      showToast('创建失败: ' + (data.detail?.message || JSON.stringify(data)), 'error');
    }
  } catch (e) {
    showToast('请求失败: ' + e.message, 'error');
  } finally {
    btn.textContent = '创建';
    btn.disabled = false;
  }
}

let _createdRawKey = '';

function copyCreatedKey() {
  const txt = document.getElementById('created-raw-key').textContent;
  navigator.clipboard.writeText(txt).then(() => {
    showToast('已复制到剪贴板', 'info');
  });
}

function closeKeyCreatedModal() {
  document.getElementById('key-created-modal').classList.add('hidden');
}

let _detailRawKey = '';  // 缓存解密后的 raw_key

async function showKeyDetail(keyId) {
  _selectedDetailKeyId = keyId;
  _detailRawKey = '';
  document.getElementById('detail-key-title').textContent = '密钥详情: ' + keyId;
  document.getElementById('btn-revoke-key').classList.add('hidden');
  document.getElementById('btn-show-raw-key').classList.add('hidden');
  document.getElementById('detail-raw-key-section').classList.add('hidden');
  document.getElementById('key-detail-content').innerHTML = '<div class="text-gray-400">加载中...</div>';
  document.getElementById('key-detail-modal').classList.remove('hidden');

  try {
    // 调用单密钥详情 API（含解密 raw_key）
    const data = await adminGet('/admin/keys/' + keyId);
    if (data && data.data) {
      const k = data.data;
      const usage = k.usage || {};
      
      document.getElementById('key-detail-content').innerHTML =
        '<div class="grid grid-cols-2 gap-3">' +
          '<div><span class="text-gray-500">标签:</span> ' + (k.label || '-') + '</div>' +
          '<div><span class="text-gray-500">权限:</span> ' + permissionBadge(k.permission) + '</div>' +
          '<div><span class="text-gray-500">状态:</span> ' + enabledBadge(k.enabled) + '</div>' +
          '<div><span class="text-gray-500">创建者:</span> ' + (k.created_by || '-') + '</div>' +
          '<div><span class="text-gray-500">创建时间:</span> ' + formatDate(k.created_at) + '</div>' +
          '<div><span class="text-gray-500">过期时间:</span> ' + formatDate(k.expires_at) + '</div>' +
          '<div><span class="text-gray-500">总调用:</span> ' + (usage.total_calls || 0) + '</div>' +
          '<div><span class="text-gray-500">最后使用:</span> ' + formatDate(usage.last_used) + '</div>' +
        '</div>';
      
      // raw_key 可用性
      if (k.raw_key) {
        _detailRawKey = k.raw_key;
        document.getElementById('btn-show-raw-key').classList.remove('hidden');
      }
      
      if (k.enabled) {
        document.getElementById('btn-revoke-key').classList.remove('hidden');
      }
    }
  } catch (e) {
    document.getElementById('key-detail-content').innerHTML = '<div class="text-red-500">加载失败: ' + e.message + '</div>';
  }
}

function showDetailRawKey() {
  if (!_detailRawKey) {
    showToast('密钥原文不可用（可能是旧版创建的密钥，仅初创时可见）', 'error');
    return;
  }
  const section = document.getElementById('detail-raw-key-section');
  document.getElementById('detail-raw-key-value').textContent = _detailRawKey;
  section.classList.remove('hidden');
  document.getElementById('btn-show-raw-key').classList.add('hidden');
}

function copyDetailRawKey() {
  if (!_detailRawKey) return;
  navigator.clipboard.writeText(_detailRawKey).then(() => {
    showToast('✅ 密钥已复制到剪贴板', 'success');
  }).catch(() => {
    // 降级：选中文本让用户手动复制
    const el = document.getElementById('detail-raw-key-value');
    const range = document.createRange();
    range.selectNodeContents(el);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    showToast('自动复制失败，请手动 Ctrl+C 复制选中的密钥', 'error');
  });
}

// 从列表直接复制密钥（调用详情接口获取 raw_key）
async function copyKeyFromDetail(keyId) {
  try {
    const data = await adminGet('/admin/keys/' + keyId);
    if (data && data.data && data.data.raw_key) {
      await navigator.clipboard.writeText(data.data.raw_key);
      showToast('✅ 密钥已复制到剪贴板', 'success');
    } else {
      showToast('❌ 密钥原文不可用（旧版创建的密钥仅初创时可见）', 'error');
    }
  } catch (e) {
    showToast('❌ 获取密钥失败: ' + e.message, 'error');
  }
}

function closeKeyDetailModal() {
  document.getElementById('key-detail-modal').classList.add('hidden');
  document.getElementById('detail-raw-key-section').classList.add('hidden');
  _detailRawKey = '';
}

async function confirmRevokeKey(keyId) {
  if (!confirm('确认撤销此密钥？撤销后所有使用此密钥的请求将被拒绝。')) return;
  try {
    const data = await adminPost('/admin/keys/' + keyId + '/revoke', {});
    if (data.status === 'success') {
      loadAdminKeys();
      showToast('密钥已撤销', 'info');
    } else {
      showToast('撤销失败: ' + (data.detail?.message || JSON.stringify(data)), 'error');
    }
  } catch (e) {
    showToast('请求失败: ' + e.message, 'error');
  }
}

async function confirmDeleteKey(keyId) {
  if (!confirm('⚠️ 确认永久删除此密钥？此操作不可恢复，删除后数据将从服务端移除。')) return;
  if (!confirm('再次确认：密钥 ' + keyId + ' 将被永久删除，无法找回。')) return;
  try {
    const resp = await fetch(API_BASE() + '/admin/keys/' + keyId, {
      method: 'DELETE',
      headers: adminHeaders('DELETE'),
    });
    const data = await resp.json();
    if (resp.ok && data.status === 'success') {
      loadAdminKeys();
      showToast('密钥已永久删除', 'info');
    } else {
      const msg = data.detail?.message || JSON.stringify(data);
      if (resp.status === 403) {
        showToast('❌ 权限不足：当前令牌无admin权限。\n请先在「连接配置」页选择一个admin令牌后再试。\n\n详情: ' + msg, 'error');
      } else if (resp.status === 404) {
        showToast('❌ 密钥不存在或已被删除: ' + msg, 'error');
      } else {
        showToast('删除失败 (' + resp.status + '): ' + msg, 'error');
      }
    }
  } catch (e) {
    showToast('请求失败: ' + e.message, 'error');
  }
}

async function revokeAdminKey() {
  if (_selectedDetailKeyId) {
    await confirmRevokeKey(_selectedDetailKeyId);
    closeKeyDetailModal();
  }
}
// ── 页面切换 ──────────────────────────────────────────────
document.querySelectorAll('.sidebar-item').forEach(item => {
  item.addEventListener('click', async function(ev) {
    // 跳过 <a> 链接（如 API 文档入口），让默认导航行为生效
    if (this.tagName === 'A') return;
    document.querySelectorAll('.sidebar-item').forEach(i => i.classList.remove('active'));
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    item.classList.add('active');
    var target = document.getElementById('page-' + item.dataset.page);
    if (!target) { console.warn('Page not found:', item.dataset.page); return; }
    target.classList.add('active');
    try {
      if (item.dataset.page === 'home') await loadDashboard();
      if (item.dataset.page === 'specs') loadSpecs();
      if (item.dataset.page === 'analysis') await loadAnalysis();
      if (item.dataset.page === 'history') renderHistoryList();
      if (item.dataset.page === 'apikeys') loadAdminKeys();
      if (item.dataset.page === 'cases') { loadCaseStats(); loadCases(0); }
      if (item.dataset.page === 'cd') loadCDItems();
      if (item.dataset.page === 'model-params') switchModelParamTab('functions');
    } catch(e) { console.error('页面加载错误:', e); }
  });
});

// ── API 调用 ──────────────────────────────────────────────
function getHeaders() {
  const key = getActiveKeyValue();
  return key ? {'Authorization': 'Bearer ' + key} : {};
}

async function apiGet(path) {
  const r = await fetch(API_BASE() + path, {method: 'GET', headers: getHeaders()});
  const data = await r.json();
  if (!r.ok) throw new Error('API错误 (' + r.status + '): ' + (data.detail || data.message || JSON.stringify(data)));
  return data;
}

async function apiPost(path, body) {
  const r = await fetch(API_BASE() + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getHeaders() },
    body: JSON.stringify(body),
  });
  const data = await r.json();
  if (!r.ok) throw new Error('API错误 (' + r.status + '): ' + (data.detail || data.message || JSON.stringify(data)));
  return data;
}

async function apiFetch(path, options = {}) {
  const r = await fetch(API_BASE() + path, {
    headers: { 'Content-Type': 'application/json', ...getHeaders(), ...options.headers },
    ...options,
  });
  return r.json();
}

async function apiPostFile(path, file, extraParams = {}) {
  const form = new FormData();
  form.append('file', file);
  const params = new URLSearchParams(extraParams);
  const url = API_BASE() + path + (params.toString() ? '?' + params.toString() : '');
  const r = await fetch(url, {method: 'POST', headers: HEADERS(), body: form});
  const data = await r.json();
  if (!r.ok) throw new Error('上传失败 (' + r.status + '): ' + (data.detail || data.message || JSON.stringify(data)));
  return data;
}

// ── 测试连接 ──────────────────────────────────────────────
async function testConnection() {
  const s = document.getElementById('conn-status');
  s.className = 'text-xs text-yellow-600';
  s.textContent = '连接中...';
  try {
    const data = await apiGet('/health');
    s.className = 'text-xs text-green-600';
    s.textContent = '✅ 连接成功 | ' + data.version + ' | 引擎: ' + data.engine_status;
  } catch (e) {
    s.className = 'text-xs text-red-600';
    s.textContent = '❌ 连接失败: ' + e.message;
  }
}

