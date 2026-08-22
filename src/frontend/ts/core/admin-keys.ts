// ── P123 Phase 1 Step 2: 后端密钥管理模块 ────────────────
// 从 baa-core.js 拆出 loadAdminKeys / createAdminKey / showKeyDetail
// 等密钥管理页面交互函数，全部走 adminGet/adminPost/adminDelete

import {
  adminGet,
  adminPost,
  adminDelete,
  setAdminToken,
  getApiBase,
} from './api-client';
import { showToast } from './toast';
import { formatDate, permissionBadge, enabledBadge, escHtml } from './utils';

interface KeyItem {
  key_id?: string;
  label?: string;
  permission?: string;
  enabled?: boolean;
  created_at?: number;
  expires_at?: number;
  created_by?: string;
  has_raw_key?: boolean;
  raw_key?: string;
  usage?: { total_calls?: number; last_used?: number };
  info?: { permission?: string; expires_at?: number };
}

interface AdminResponse {
  status?: string;
  data?: KeyItem | Array<KeyItem> | Record<string, unknown>;
  detail?: Record<string, unknown>;
}

let _selectedDetailKeyId = '';
let _detailRawKey = '';

export async function initAdminToken(): Promise<void> {
  try {
    const r = await fetch(getApiBase() + '/admin/bootstrap-key');
    if (r.ok) {
      const d = (await r.json()) as AdminResponse;
      if (d.status === 'success') setAdminToken((d as Record<string, string>).admin_key || '');
    }
  } catch {
    /* dev mode */
  }
}

export async function loadAdminKeys(): Promise<void> {
  const table = document.getElementById('admin-keys-table') as HTMLElement | null;
  if (!table) return;
  table.innerHTML = '<div class="text-center py-8 text-gray-400 text-sm">加载中...</div>';

  try {
    const showDisabled = (document.getElementById('show-disabled') as HTMLInputElement | null)?.checked;
    const data = (await adminGet(`/admin/keys?include_disabled=${showDisabled ? 'true' : 'false'}`)) as AdminResponse;
    const statsData = (await adminGet('/admin/keys/stats')) as AdminResponse;

    if (statsData?.data && typeof statsData.data === 'object' && !Array.isArray(statsData.data)) {
      const s = ((statsData.data as Record<string, unknown>).summary as Record<string, number>) || {};
      ['stat-total', 'stat-active', 'stat-disabled', 'stat-calls'].forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.textContent = String(s[id] ?? 0);
      });
    }

    const items = Array.isArray(data?.data) ? data.data : [];
    if (items.length === 0) {
      table.innerHTML = '<div class="text-center py-8 text-gray-400 text-sm">暂无密钥，点击「+ 创建密钥」开始</div>';
      return;
    }

    let html =
      '<table class="w-full text-sm"><thead><tr class="text-left text-gray-500 border-b">' +
      '<th class="pb-2 pr-3">标签</th><th class="pb-2 pr-3">权限</th><th class="pb-2 pr-3">状态</th>' +
      '<th class="pb-2 pr-3">创建</th><th class="pb-2 pr-3">过期</th><th class="pb-2 pr-3">调用</th>' +
      '<th class="pb-2">操作</th></tr></thead><tbody>';

    for (const k of items) {
      const usage = (k.usage as Record<string, number>) || {};
      html +=
        '<tr class="border-b hover:bg-gray-50">' +
        `<td class="py-2 pr-3 font-medium">${escHtml(k.label || '-')}</td>` +
        `<td class="py-2 pr-3">${permissionBadge(String(k.permission))}</td>` +
        `<td class="py-2 pr-3">${enabledBadge(Boolean(k.enabled))}</td>` +
        `<td class="py-2 pr-3 text-gray-500">${formatDate(k.created_at)}</td>` +
        `<td class="py-2 pr-3 text-gray-500">${formatDate(k.expires_at)}</td>` +
        `<td class="py-2 pr-3 text-gray-500">${usage.total_calls || 0}</td>` +
        '<td class="py-2">' +
        `<button onclick="showKeyDetail('${escHtml(k.key_id || '')}')" class="px-2 py-1 bg-gray-200 rounded text-xs hover:bg-gray-300 mr-1">详情</button>` +
        (k.has_raw_key
          ? `<button onclick="copyKeyFromDetail('${escHtml(k.key_id || '')}')" class="px-2 py-1 bg-blue-100 rounded text-xs hover:bg-blue-200 mr-1">📋复制</button>`
          : '') +
        (k.enabled
          ? `<button onclick="confirmRevokeKey('${escHtml(k.key_id || '')}')" class="px-2 py-1 bg-red-100 rounded text-xs hover:bg-red-200 mr-1">撤销</button>`
          : '') +
        `<button onclick="confirmDeleteKey('${escHtml(k.key_id || '')}')" class="px-2 py-1 bg-red-200 rounded text-xs hover:bg-red-300">🗑️</button>` +
        '</td></tr>';
    }
    table.innerHTML = html + '</tbody></table>';
  } catch (e) {
    table.innerHTML = `<div class="text-center py-8 text-red-500 text-sm">❌ 加载失败: ${escHtml((e as Error).message)}</div>`;
  }
}

export function openCreateKeyModal(): void {
  document.getElementById('create-key-modal')?.classList.remove('hidden');
  const label = document.getElementById('new-key-label') as HTMLInputElement | null;
  if (label) label.value = '';
  const perm = document.getElementById('new-key-permission') as HTMLSelectElement | null;
  if (perm) perm.value = 'write';
  const ttl = document.getElementById('new-key-ttl') as HTMLInputElement | null;
  if (ttl) ttl.value = '90';
}

export function closeCreateKeyModal(): void {
  document.getElementById('create-key-modal')?.classList.add('hidden');
}

export async function createAdminKey(): Promise<void> {
  const label = ((document.getElementById('new-key-label') as HTMLInputElement) || {}).value?.trim() || 'unnamed';
  const permission = ((document.getElementById('new-key-permission') as HTMLSelectElement) || {}).value || 'write';
  const ttl = parseInt(((document.getElementById('new-key-ttl') as HTMLInputElement) || {}).value || '90');
  const btn = document.querySelector('#create-key-modal .bg-green-600') as HTMLButtonElement | null;
  if (btn) { btn.textContent = '创建中...'; btn.disabled = true; }

  try {
    const data = (await adminPost('/admin/keys', { label, permission, ttl_days: ttl })) as AdminResponse;
    if (data?.status === 'success' && data.data && typeof data.data === 'object') {
      closeCreateKeyModal();
      const raw = document.getElementById('created-raw-key') as HTMLElement | null;
      if (raw) raw.textContent = String((data.data as KeyItem).raw_key || '');
      const info = document.getElementById('created-key-key-info') as HTMLElement | null;
      const d = data.data as KeyItem;
      if (info) info.innerHTML = `密钥ID: ${escHtml(d.key_id || '-')}<br>权限: ${escHtml(d.info?.permission || '-')}<br>过期: ${formatDate(d.info?.expires_at)}`;
      document.getElementById('key-created-modal')?.classList.remove('hidden');
      await loadAdminKeys();
    } else {
      showToast(`创建失败: ${JSON.stringify(data?.detail)}`, 'error');
    }
  } catch (e) {
    showToast(`请求失败: ${(e as Error).message}`, 'error');
  } finally {
    if (btn) { btn.textContent = '创建'; btn.disabled = false; }
  }
}

export function copyCreatedKey(): void {
  const txt = document.getElementById('created-raw-key')?.textContent || '';
  navigator.clipboard.writeText(txt).then(() => showToast('已复制到剪贴板', 'info'));
}

export function closeKeyCreatedModal(): void {
  document.getElementById('key-created-modal')?.classList.add('hidden');
}

export async function showKeyDetail(keyId: string): Promise<void> {
  _selectedDetailKeyId = keyId;
  _detailRawKey = '';
  const title = document.getElementById('detail-key-title') as HTMLElement | null;
  if (title) title.textContent = `密钥详情: ${escHtml(keyId)}`;
  document.getElementById('btn-revoke-key')?.classList.add('hidden');
  document.getElementById('btn-show-raw-key')?.classList.add('hidden');
  document.getElementById('detail-raw-key-section')?.classList.add('hidden');
  const content = document.getElementById('key-detail-content') as HTMLElement | null;
  if (content) content.innerHTML = '<div class="text-gray-400">加载中...</div>';
  document.getElementById('key-detail-modal')?.classList.remove('hidden');

  try {
    const data = (await adminGet(`/admin/keys/${keyId}`)) as AdminResponse;
    if (data?.data && typeof data.data === 'object') {
      const k = data.data as KeyItem;
      const usage = (k.usage as Record<string, number>) || {};
      if (content)
        content.innerHTML =
          '<div class="grid grid-cols-2 gap-3">' +
          `<div><span class="text-gray-500">标签:</span> ${escHtml(k.label || '-')}</div>` +
          `<div><span class="text-gray-500">权限:</span> ${permissionBadge(String(k.permission))}</div>` +
          `<div><span class="text-gray-500">状态:</span> ${enabledBadge(Boolean(k.enabled))}</div>` +
          `<div><span class="text-gray-500">创建者:</span> ${escHtml(k.created_by || '-')}</div>` +
          `<div><span class="text-gray-500">创建:</span> ${formatDate(k.created_at)}</div>` +
          `<div><span class="text-gray-500">过期:</span> ${formatDate(k.expires_at)}</div>` +
          `<div><span class="text-gray-500">总调用:</span> ${usage.total_calls || 0}</div>` +
          `<div><span class="text-gray-500">最后使用:</span> ${formatDate(usage.last_used)}</div>` +
          '</div>';
      if (k.raw_key) {
        _detailRawKey = String(k.raw_key);
        document.getElementById('btn-show-raw-key')?.classList.remove('hidden');
      }
      if (k.enabled) document.getElementById('btn-revoke-key')?.classList.remove('hidden');
    }
  } catch (e) {
    if (content) content.innerHTML = `<div class="text-red-500">加载失败: ${escHtml((e as Error).message)}</div>`;
  }
}

export function showDetailRawKey(): void {
  if (!_detailRawKey) {
    showToast('密钥原文不可用（旧版创建的密钥仅初创时可见）', 'error');
    return;
  }
  const section = document.getElementById('detail-raw-key-section') as HTMLElement | null;
  const val = document.getElementById('detail-raw-key-value') as HTMLElement | null;
  if (val) val.textContent = _detailRawKey;
  section?.classList.remove('hidden');
  document.getElementById('btn-show-raw-key')?.classList.add('hidden');
}

export function copyDetailRawKey(): void {
  if (!_detailRawKey) return;
  navigator.clipboard.writeText(_detailRawKey).then(
    () => showToast('✅ 密钥已复制到剪贴板', 'success'),
    () => showToast('自动复制失败，请手动 Ctrl+C', 'error'),
  );
}

export async function copyKeyFromDetail(keyId: string): Promise<void> {
  try {
    const data = (await adminGet(`/admin/keys/${keyId}`)) as AdminResponse;
    const raw = (data?.data as KeyItem)?.raw_key;
    if (raw) {
      await navigator.clipboard.writeText(String(raw));
      showToast('✅ 密钥已复制到剪贴板', 'success');
    } else {
      showToast('❌ 密钥原文不可用', 'error');
    }
  } catch (e) {
    showToast(`❌ 获取密钥失败: ${(e as Error).message}`, 'error');
  }
}

export function closeKeyDetailModal(): void {
  document.getElementById('key-detail-modal')?.classList.add('hidden');
  document.getElementById('detail-raw-key-section')?.classList.add('hidden');
  _detailRawKey = '';
}

export async function confirmRevokeKey(keyId: string): Promise<void> {
  if (!confirm(`确认撤销密钥 ${keyId}？`)) return;
  try {
    const data = await adminPost(`/admin/keys/${keyId}/revoke`, {});
    if ((data as AdminResponse).status === 'success') {
      await loadAdminKeys();
      showToast('密钥已撤销', 'info');
    } else {
      showToast(`撤销失败: ${JSON.stringify((data as AdminResponse).detail)}`, 'error');
    }
  } catch (e) {
    showToast(`请求失败: ${(e as Error).message}`, 'error');
  }
}

export async function confirmDeleteKey(keyId: string): Promise<void> {
  if (!confirm(`⚠️ 确认永久删除密钥 ${keyId}？`)) return;
  if (!confirm('再次确认：该密钥将被永久删除，无法找回。')) return;
  try {
    const resp = await adminDelete(`/admin/keys/${keyId}`);
    if ((resp as AdminResponse).status === 'success') {
      await loadAdminKeys();
      showToast('密钥已永久删除', 'info');
    } else {
      showToast(`删除失败: ${JSON.stringify((resp as AdminResponse).detail)}`, 'error');
    }
  } catch (e) {
    showToast(`请求失败: ${(e as Error).message}`, 'error');
  }
}

export async function revokeAdminKey(): Promise<void> {
  if (_selectedDetailKeyId) {
    await confirmRevokeKey(_selectedDetailKeyId);
    closeKeyDetailModal();
  }
}

if (typeof window !== 'undefined') {
  window.initAdminToken = initAdminToken;
  window.loadAdminKeys = loadAdminKeys;
  window.openCreateKeyModal = openCreateKeyModal;
  window.closeCreateKeyModal = closeCreateKeyModal;
  window.createAdminKey = createAdminKey;
  window.copyCreatedKey = copyCreatedKey;
  window.closeKeyCreatedModal = closeKeyCreatedModal;
  window.showKeyDetail = showKeyDetail;
  window.showDetailRawKey = showDetailRawKey;
  window.copyDetailRawKey = copyDetailRawKey;
  window.copyKeyFromDetail = copyKeyFromDetail;
  window.closeKeyDetailModal = closeKeyDetailModal;
  window.confirmRevokeKey = confirmRevokeKey;
  window.confirmDeleteKey = confirmDeleteKey;
  window.revokeAdminKey = revokeAdminKey;
}