// ── P123 Phase 1 Step 2: API 密钥管理模块 ─────────────────
// 从 baa-core.js 拆出本地 apiKeys 管理和 import 逻辑
// 旧 .js 文件通过 window 全局访问，此处兼容挂载

import { showToast } from './toast';
import { maskKey, escHtml } from './utils';

interface LocalKey {
  id: string;
  name: string;
  key: string;
  created: number;
}

let _keys: LocalKey[] = [];
let _activeKey: string = '';

/** 加载本地密钥列表 */
export function loadKeys(): void {
  try {
    const stored = localStorage.getItem('baa_api_keys');
    _keys = stored ? (JSON.parse(stored) as LocalKey[]) : [];
    _activeKey = localStorage.getItem('baa_active_key') || '';
  } catch {
    _keys = [];
    _activeKey = '';
  }
  populateTokenSelect();
}

/** 保存本地密钥列表 */
export function saveKeys(): void {
  localStorage.setItem('baa_api_keys', JSON.stringify(_keys));
}

/** 获取活跃密钥原始值 */
export function getActiveKeyValue(): string {
  const k = _keys.find((k) => k.id === _activeKey);
  return k ? k.key : '';
}

/** 获取本地密钥列表引用（供状态模块使用） */
export function getKeys(): LocalKey[] {
  return _keys;
}

export function setActiveKey(id: string): void {
  _activeKey = id;
  localStorage.setItem('baa_active_key', _activeKey);
  populateTokenSelect();
}

/** 填充下拉选择器 */
export function populateTokenSelect(): void {
  const select = document.getElementById('active-key-select') as HTMLSelectElement | null;
  if (!select) return;
  select.innerHTML = '<option value="">无令牌（开发模式）</option>';
  _keys.forEach((k) => {
    const opt = document.createElement('option');
    opt.value = k.id;
    opt.textContent = `${k.name} (${maskKey(k.key)})`;
    if (k.id === _activeKey) opt.selected = true;
    select.appendChild(opt);
  });
  const hint = document.getElementById('token-hint') as HTMLElement | null;
  if (hint) {
    hint.textContent =
      _keys.length > 0
        ? `共 ${_keys.length} 个本地令牌。外部项目的token可手动添加。`
        : '暂无令牌。可在「密钥管理」页面创建后在此添加，或点击下方手动输入。';
  }
}

export function switchApiKey(id: string): void {
  setActiveKey(id);
}

export function deleteCurrentApiKey(): void {
  if (!_activeKey) {
    showToast('当前没有选中任何令牌', 'info');
    return;
  }
  if (!confirm('确认删除当前令牌？')) return;
  deleteApiKey(_activeKey);
}

export function addApiKey(): void {
  const name = prompt('令牌名称（如：EMA2对接）');
  if (!name) return;
  const key = prompt('请输入令牌内容（从密钥管理页面复制）');
  if (!key) return;
  _keys.push({ id: `key_${Date.now()}`, name, key, created: Date.now() });
  saveKeys();
  _activeKey = _keys[_keys.length - 1].id;
  localStorage.setItem('baa_active_key', _activeKey);
  populateTokenSelect();
}

export function deleteApiKey(id: string): void {
  if (!confirm('确认删除此本地令牌？')) return;
  _keys = _keys.filter((k) => k.id !== id);
  if (_activeKey === id) {
    _activeKey = _keys.length > 0 ? _keys[_keys.length - 1].id : '';
    localStorage.setItem('baa_active_key', _activeKey);
  }
  saveKeys();
  populateTokenSelect();
}

export function copyApiKey(id: string): void {
  const k = _keys.find((k) => k.id === id);
  if (!k) return;
  navigator.clipboard.writeText(k.key).then(
    () => showToast('令牌已复制到剪贴板', 'info'),
    () => showToast('复制失败，请手动复制', 'error'),
  );
}

// ── 向后兼容 ──────────────────────────────────────────────
if (typeof window !== 'undefined') {
  window.getApiKey = () => getActiveKeyValue();
  window.getActiveKeyValue = getActiveKeyValue;
  window.loadApiKeys = loadKeys;
  window.saveApiKeys = saveKeys;
  window.switchApiKey = switchApiKey;
  window.deleteCurrentApiKey = deleteCurrentApiKey;
  window.addApiKey = addApiKey;
  window.deleteApiKey = deleteApiKey;
  window.copyApiKey = copyApiKey;
  window.populateTokenSelect = populateTokenSelect;
}