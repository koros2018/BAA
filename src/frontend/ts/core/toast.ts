// ── P123 Phase 1: Toast 通知系统 ──────────────────────────
// 从 baa-core.js showToast() 拆出，保留向后兼容的 window.showToast()

import type { ToastType } from './types';

const ICONS: Record<ToastType['type'], string> = {
  info: 'ℹ️',
  success: '✅',
  error: '❌',
  warn: '⚠️',
};

/**
 * 显示右下角 Toast 通知
 * @param message 通知文本
 * @param type 类型 (默认 info)
 * @param duration 持续时间 ms (默认 4000)
 */
export function showToast(
  message: string,
  type: ToastType['type'] = 'info',
  duration = 4000,
): void {
  if (typeof message !== 'string' || !message) return;

  const container = (() => {
    let c = document.getElementById('toast-container') as HTMLDivElement | null;
    if (!c) {
      c = document.createElement('div');
      c.id = 'toast-container';
      c.className = 'toast-container';
      document.body.appendChild(c);
    }
    return c;
  })();

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<span>${ICONS[type] || 'ℹ️'}</span><span>${message}</span>`;
  container.appendChild(toast);

  if (container.children.length > 5) {
    container.firstChild?.remove();
  }

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(20px)';
  }, duration);

  setTimeout(() => {
    if (toast.parentNode) toast.parentNode.removeChild(toast);
  }, duration + 300);
}

// 向后兼容：挂载到 window
if (typeof window !== 'undefined') {
  window.showToast = showToast;
}