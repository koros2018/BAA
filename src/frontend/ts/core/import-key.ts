// ── P123 Phase 1 Step 3: 密钥导入弹窗模块 ─────────────────
// 从 baa-core.js 拆出 importServerKey / importSelectedKey / closeImportKeyModal
// index.html 通过 onclick 调用 importServerKey() / closeImportKeyModal()

import { apiGet, apiPostJSON } from './api-client';
import { showToast } from './toast';
import { formatDate, escHtml } from './utils';

let _importingKeyId: string | null = null;

/** 获取本地活跃密钥值（不依赖 key-manager 循环导入） */
function getActiveKeyValue(): string {
  const activeId = localStorage.getItem('baa_active_key') || '';
  if (!activeId) return '';
  try {
    const keys = JSON.parse(localStorage.getItem('baa_api_keys') || '[]') as Array<Record<string, unknown>>;
    const k = keys.find((k) => String(k.id) === activeId);
    return k ? String(k.key || '') : '';
  } catch {
    return '';
  }
}

/** 打开密钥导入弹窗，加载后端可用密钥列表 */
export async function importServerKey(): Promise<void> {
  const activeKeyVal = getActiveKeyValue();
  if (!activeKeyVal) {
    if (
      !confirm(
        '当前未选择任何令牌，后端 /admin/keys 需要admin权限。\n' +
          '是否仍要尝试？（建议先在「密钥管理」创建admin密钥后选择）',
      )
    ) {
      return;
    }
  }

  const list = document.getElementById('import-key-list') as HTMLElement | null;
  if (!list) {
    showToast('页面元素异常', 'info');
    return;
  }
  list.innerHTML = '<div class="text-center text-gray-400 text-sm py-4">⏳ 加载中...</div>';
  const modal = document.getElementById('import-key-modal') as HTMLElement | null;
  modal?.classList.remove('hidden');

  try {
    const data = (await apiGet('/admin/keys')) as Record<string, unknown>;
    const keys = data?.data as Array<Record<string, unknown>> | undefined;
    if (!keys || keys.length === 0) {
      list.innerHTML =
        '<div class="text-center text-gray-400 text-sm py-4">暂无可用密钥，请先在「密钥管理」页面创建。</div>';
      return;
    }

    const detail = data?.detail as Record<string, unknown> | undefined;
    if (detail && detail.error_code === 'FORBIDDEN') {
      list.innerHTML =
        '<div class="text-center text-red-500 text-sm py-4">❌ 权限不足：当前令牌无admin权限。\n' +
        '请先在「密钥管理」页面创建admin密钥，\n' +
        '然后在连接配置页选择该令牌后再试。</div>';
      return;
    }

    list.innerHTML = '';
    for (const k of keys) {
      if (!k.enabled) continue;
      const div = document.createElement('div');
      const label = escHtml(String(k.label || k.key_id));
      const expires = k.expires_at
        ? '过期: ' + formatDate(String(k.expires_at))
        : '永不过期';
      const keyId = escHtml(String(k.key_id || ''));
      div.className =
        'flex items-center justify-between p-3 border rounded-lg hover:bg-gray-50 cursor-pointer';
      div.innerHTML =
        '<div class="flex-1 min-w-0">' +
          `<div class="font-medium text-sm">${label}</div>` +
          `<div class="text-xs text-gray-400">权限: ${escHtml(String(k.permission))} | ${expires}</div>` +
        '</div>' +
        `<button onclick="importSelectedKey('${keyId}')" class="px-3 py-1.5 bg-purple-600 text-white rounded text-xs hover:bg-purple-700 shrink-0">选择并填入</button>`;
      list.appendChild(div);
    }
  } catch (e) {
    list.innerHTML = `<div class="text-center text-red-500 text-sm py-4">❌ 加载失败: ${escHtml((e as Error).message)}</div>`;
  }
}

/** 用户选择了某个后端密钥，验证并导入到本地 */
export async function importSelectedKey(keyId: string): Promise<void> {
  _importingKeyId = keyId;
  const keyValue = prompt(`请输入此密钥的原始值（从密钥管理页创建时复制）：`);
  if (!keyValue) return;

  const btn = ((event?.target as HTMLButtonElement) || document.querySelector('#import-key-modal button')) as HTMLButtonElement | null;
  if (btn) {
    btn.textContent = '验证中...';
    btn.disabled = true;
  }

  try {
    const verifyResult = await apiPostJSON('/admin/keys/verify', { raw_key: keyValue });
    const vr = verifyResult as Record<string, unknown>;
    if (vr.status === 'success' && vr.valid) {
      const keyInfo = (vr.key_info || {}) as Record<string, unknown>;
      const label = (String(keyInfo.label || keyInfo.key_id || keyId) + ' (imported)');
      const id = `key_${Date.now()}`;
      // 写入本地密钥
      const stored = localStorage.getItem('baa_api_keys');
      const keys = stored ? (JSON.parse(stored) as Array<Record<string, unknown>>) : [];
      keys.push({ id, name: label, key: keyValue, created: Date.now() });
      localStorage.setItem('baa_api_keys', JSON.stringify(keys));
      localStorage.setItem('baa_active_key', id);
      // 刷新下拉
      const populate = (window as unknown as Record<string, unknown>).populateTokenSelect;
      if (typeof populate === 'function') (populate as () => void)();
      closeImportKeyModal();
      showToast('✅ 密钥验证通过，已添加到本地令牌列表', 'success');
    } else {
      showToast(
        '❌ 密钥验证失败：' + (String(vr.message || '密钥无效或已过期')),
        'error',
      );
    }
  } catch (e) {
    if (
      confirm('无法验证密钥有效性（' + (e as Error).message + '）。是否仍要保存到本地？')
    ) {
      const id = `key_${Date.now()}`;
      const stored = localStorage.getItem('baa_api_keys');
      const keys = stored ? (JSON.parse(stored) as Array<Record<string, unknown>>) : [];
      keys.push({ id, name: keyId + ' (imported)', key: keyValue, created: Date.now() });
      localStorage.setItem('baa_api_keys', JSON.stringify(keys));
      localStorage.setItem('baa_active_key', id);
      const populate = (window as unknown as Record<string, unknown>).populateTokenSelect;
      if (typeof populate === 'function') (populate as () => void)();
      closeImportKeyModal();
    }
  } finally {
    if (btn) {
      btn.textContent = '选择并填入';
      btn.disabled = false;
    }
  }
}


/** 关闭密钥导入弹窗 */
export function closeImportKeyModal(): void {
  document.getElementById('import-key-modal')?.classList.add('hidden');
}

// 向后兼容
if (typeof window !== 'undefined') {
  const w = window as unknown as Record<string, unknown>;
  w.importServerKey = importServerKey;
  w.importSelectedKey = importSelectedKey;
  w.closeImportKeyModal = closeImportKeyModal;
}