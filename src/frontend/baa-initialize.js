// ── 初始化 ──────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadApiBase();  // 恢复API地址
  initAdminToken();  // 初始化密钥管理页专用管理令牌
  loadApiKeys();
  populateTokenSelect();

  // API地址变更时自动保存
  document.getElementById('api-base')?.addEventListener('change', saveApiBase);

  // 引擎状态（概览页用）
  try {
    const healthEl = document.getElementById('health-status');
    if (healthEl) {
      const health = JSON.parse(healthEl.textContent || '{}');
    }
  } catch(e) {}

  // 页面加载后异步加载规范库
  if (typeof loadSpecs === 'function') {
    loadSpecs();
  }

  // 引擎状态由 baa-admin.js 中的 initAdminToken 更新
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

