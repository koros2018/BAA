// ── P123 Phase 2: Modal 弹窗组件 ─────────────────────────
// 通用弹窗：替代 baa-admin.js / baa-audit.js / baa-core.js 中的
// 内联 modal HTML + classList 手动切换模式
// 用法: openModal({title, content, footerButtons, size}) 返回关闭回调

import { showToast } from '../core/toast';

export interface ModalButton {
  label: string;
  cls?: string;
  onClick: () => void;
}

export interface ModalOptions {
  title?: string;
  content: string | HTMLElement;
  footerButtons?: ModalButton[];
  size?: 'sm' | 'md' | 'lg' | 'xl';
  onClose?: () => void;
  closeOnOverlay?: boolean;
  id?: string;
}

let _activeModalId = 0;
const _sizeCls: Record<string, string> = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-2xl',
};

/**
 * 打开弹窗
 * @returns 关闭回调函数
 */
export function openModal(options: ModalOptions): () => void {
  const id = options.id || `modal-${++_activeModalId}`;
  const size = _sizeCls[options.size || 'md'];

  // 若已存在，复用
  let overlay = document.getElementById(id) as HTMLElement | null;
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = id;
    overlay.className =
      'fixed inset-0 bg-black/40 flex items-center justify-center z-50 transition-opacity duration-200';
    overlay.style.opacity = '0';
    overlay.style.pointerEvents = 'none';
    document.body.appendChild(overlay);
  }

  const title = options.title || '';
  const footerHtml = options.footerButtons
    ? options.footerButtons
        .map(
          (b) =>
            `<button class="px-3 py-1.5 rounded text-xs ${b.cls || 'bg-gray-600 text-white hover:bg-gray-700'}" data-btn="${b.label}">${b.label}</button>`,
        )
        .join(' ')
    : '';

  let contentHtml = '';
  if (typeof options.content === 'string') {
    contentHtml = options.content;
  } else if (options.content instanceof HTMLElement) {
    const wrapper = document.createElement('div');
    wrapper.appendChild(options.content.cloneNode(true));
    contentHtml = wrapper.innerHTML;
  }

  overlay.innerHTML =
    `<div class="bg-white rounded-lg shadow-xl w-full mx-4 ${size} max-h-[90vh] overflow-y-auto">` +
    (title
      ? `<div class="flex items-center justify-between p-4 border-b">` +
          `<h3 class="text-sm font-medium">${title}</h3>` +
          `<button class="text-gray-400 hover:text-gray-600 text-lg" data-close>&times;</button>` +
        `</div>`
      : '') +
    `<div class="p-4">${contentHtml}</div>` +
    (footerHtml
      ? `<div class="flex justify-end gap-2 p-4 border-t bg-gray-50">${footerHtml}</div>`
      : '') +
    `</div>`;

  // 注册关闭
  overlay.querySelectorAll('[data-close]').forEach((btn) => {
    (btn as HTMLElement).addEventListener('click', () => closeModal(id, options));
  });
  if (options.closeOnOverlay) {
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) closeModal(id, options);
    });
  }

  // 注册 footer 按钮
  if (options.footerButtons) {
    overlay.querySelectorAll('[data-btn]').forEach((btn) => {
      const label = (btn as HTMLElement).dataset.btn || '';
      const match = options.footerButtons?.find((b) => b.label === label);
      if (match) {
        (btn as HTMLElement).addEventListener('click', () => {
          match.onClick();
        });
      }
    });
  }

  // 显示
  requestAnimationFrame(() => {
    overlay.style.opacity = '1';
    overlay.style.pointerEvents = 'auto';
  });

  return () => closeModal(id, options);
}

function closeModal(id: string, options: ModalOptions): void {
  const overlay = document.getElementById(id) as HTMLElement | null;
  if (!overlay) return;
  overlay.style.opacity = '0';
  overlay.style.pointerEvents = 'none';
  setTimeout(() => overlay.remove(), 200);
  options.onClose?.();
}

/** 关闭指定弹窗 */
export function closeModalById(id: string): void {
  const overlay = document.getElementById(id) as HTMLElement | null;
  overlay?.remove();
}

// 向后兼容
if (typeof window !== 'undefined') {
  (window as unknown as Record<string, unknown>).openModal = openModal;
}