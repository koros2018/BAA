// ── P123 Phase 1: 纯工具函数（无 DOM 依赖） ─────────────
// 从 baa-core.js 拆出，纯函数可测试

/** 格式化 ISO 日期为中文 locale 字符串 */
export function formatDate(iso: number | string | undefined | null): string {
  if (!iso) return '-';
  const d = new Date(typeof iso === 'number' ? iso * 1000 : iso);
  if (isNaN(d.getTime())) return '-';
  return d.toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
}

/** 屏蔽密钥，保留前后各4位 */
export function maskKey(key: string): string {
  if (!key || key.length <= 8) return key || '';
  return key.slice(0, 4) + '...' + key.slice(-4);
}

/** HTML 转义，防 XSS */
export function escHtml(text: unknown): string {
  const s = String(text ?? '');
  const map: Record<string, string> = {
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  };
  return s.replace(/[&<>"']/g, (c) => map[c] || c);
}

/** 权限徽章 HTML */
export function permissionBadge(perm: string): string {
  const colors: Record<string, string> = {
    admin: 'bg-red-100 text-red-800',
    write: 'bg-blue-100 text-blue-800',
    read: 'bg-green-100 text-green-800',
    limited: 'bg-gray-100 text-gray-800',
  };
  const c = colors[perm] || 'bg-gray-100';
  return `<span class="inline-block px-2 py-0.5 rounded text-xs font-medium ${c}">${escHtml(perm)}</span>`;
}

/** 启用/禁用状态徽章 */
export function enabledBadge(enabled: boolean): string {
  if (enabled)
    return '<span class="inline-block px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700">✓ 启用</span>';
  return '<span class="inline-block px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700">✗ 已禁用</span>';
}

/** 唯一 ID 生成 */
export function uid(): string {
  return `id_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

export function mergeDeep(
  target: Record<string, unknown>,
  source: Record<string, unknown>,
): Record<string, unknown> {
  const out = { ...target };
  for (const key in source) {
    if (source[key] && typeof source[key] === 'object' && !Array.isArray(source[key])) {
      out[key] = mergeDeep(
        (out[key] || {}) as Record<string, unknown>,
        source[key] as Record<string, unknown>,
      );
    } else {
      out[key] = source[key];
    }
  }
  return out;
}