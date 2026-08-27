// ── P123 Step 8: 工具函数 ─────────────────────────────
// formatTimeAgo / copyReverseDXF
// expandReverseSVG / downloadReverseSVG 依赖 reverse-engine.ts（尚未迁入），暂不导出

import { showToast } from '../core/toast';

export function formatTimeAgo(isoStr: string): string {
  if (!isoStr) return '';
  const date = new Date(isoStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffHour = Math.floor(diffMs / 3600000);
  const diffDay = Math.floor(diffMs / 86400000);
  if (diffMin < 1) return '刚刚';
  if (diffMin < 60) return diffMin + '分钟前';
  if (diffHour < 24) return diffHour + '小时前';
  return diffDay + '天前';
}

export function copyReverseDXF(): void {
  const dxf = document.getElementById('reverse-dxf') as HTMLElement | null;
  if (dxf) { navigator.clipboard.writeText(dxf.textContent).then(() => showToast('DXF 已复制到剪贴板', 'info')); }
}
