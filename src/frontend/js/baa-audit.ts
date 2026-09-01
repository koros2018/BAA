/**
 * P119 违规审核工作流 — 前端交互
 *
 * 功能：
 * - 审查完成后自动初始化审核条目
 * - 违规列表每条追加 [✓确认][✗误报][?待核实][批注] 操作列
 * - 顶部统计条：已审核 X/总数 Y | 确认 C | 误报 D | 待核实 P
 * - 筛选下拉：全部/未审核/已确认/已驳回/待核实
 * - 误报按钮弹窗要求输入原因
 * - 审核完成显示"生成整改通知单"按钮
 *
 * 集成方式：baa-review.js 在 renderViolations 中调用 P119Audit.init()
 */

interface AuditStats {
  total: number;
  confirmed: number;
  dismissed: number;
  pending: number;
  unreviewed: number;
}

interface AuditItem {
  id: string;
  function_id: string;
  entity_id: string;
  status: "unreviewed" | "confirmed" | "dismissed" | "pending";
  note?: string;
}

interface AuditApiResp {
  stats?: AuditStats;
  items?: AuditItem[];
  status?: string;
}

interface AuditState {
  reviewId: string;
  stats: AuditStats;
  filter: string;
  initialized: boolean;
}

const P119Audit = (() => {
  "use strict";

  let _state: AuditState = {
    reviewId: "",
    stats: { total: 0, confirmed: 0, dismissed: 0, pending: 0, unreviewed: 0 },
    filter: "",
    initialized: false,
  };

  async function api(path: string, options: RequestInit = {}): Promise<AuditApiResp> {
    const url = (window as any).BAA_API_BASE + path;
    const opts: RequestInit = {
      method: "GET",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      ...options,
    };
    const tk = localStorage.getItem("baa_audit_token") || localStorage.getItem("auth_token");
    if (tk) (opts.headers as Record<string, string>)["Authorization"] = "Bearer " + tk;
    const r = await fetch(url, opts);
    if (!r.ok) {
      const d = await r.json();
      const err = new Error(d.detail || "API error") as Error & { status: number; detail: string };
      err.status = r.status;
      err.detail = d.detail;
      throw err;
    }
    return r.json();
  }

  function escHtml(s: unknown): string {
    if (s == null) return "";
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  async function refreshStats(): Promise<void> {
    const d = await api(`/api/v1/audit/stats?review_id=${encodeURIComponent(_state.reviewId)}`);
    _state.stats = Object.assign(
      { total: 0, confirmed: 0, dismissed: 0, pending: 0, unreviewed: 0 },
      d.stats
    );
    _renderStatsBar();
    _renderCompletedButton();
  }

  function _renderStatsBar(): void {
    const bar = document.getElementById("p119-stats-bar");
    if (!bar) return;
    const s = _state.stats;
    const done = s.confirmed + s.dismissed;
    bar.innerHTML =
      '<div class="p119-stats-row">' +
      '<span class="p119-stats-total">已审核 <strong>' + done + '</strong>/' + s.total + "</span>" +
      '<span class="p119-stat p119-stat-confirmed">确认 ' + s.confirmed + "</span>" +
      '<span class="p119-stat p119-stat-dismissed">误报 ' + s.dismissed + "</span>" +
      '<span class="p119-stat p119-stat-pending">待核实 ' + s.pending + "</span>" +
      '<span class="p119-stat p119-stat-unreviewed">未审 ' + s.unreviewed + "</span>" +
      '<select id="p119-filter" class="p119-filter">' +
      '<option value="">全部</option><option value="unreviewed">未审核</option>' +
      '<option value="confirmed">已确认</option><option value="dismissed">已驳回</option>' +
      '<option value="pending">待核实</option>' +
      "</select>" +
      "</div>";
    const sel = document.getElementById("p119-filter") as HTMLSelectElement | null;
    if (sel) {
      sel.value = _state.filter;
      sel.onchange = () => {
        _state.filter = sel.value;
        _refreshItems();
      };
    }
  }

  function _renderCompletedButton(): void {
    const holder = document.getElementById("p119-completed-holder");
    if (!holder) return;
    holder.innerHTML = "";
    const s = _state.stats;
    if (s.total > 0 && s.unreviewed === 0) {
      const btn = document.createElement("button");
      btn.className = "p119-btn-confirm";
      btn.textContent = "📋 生成整改通知单";
      btn.onclick = () => {
        (window as any).showToast?.("整改通知单生成功能（P116）开发中", "info");
      };
      holder.appendChild(btn);
    }
  }

  async function _refreshItems(): Promise<void> {
    try {
      const filterParam = _state.filter ? `&status=${encodeURIComponent(_state.filter)}` : "";
      const d = await api(
        `/api/v1/audit/items?review_id=${encodeURIComponent(_state.reviewId)}${filterParam}`
      );
      const items = d.items || [];
      const bar = document.getElementById("p119-stats-bar");
      if (!bar || !bar.dataset.itemsSlot) return;
      const slot = bar.parentElement?.querySelector(".p119-items-list");
      if (!slot) return;
      if (items.length === 0) {
        slot.innerHTML = '<div class="p119-empty">无匹配记录</div>';
        return;
      }
      slot.innerHTML = items
        .map((it) => {
          const cls = "p119-item p119-item-" + it.status;
          const statusLabel =
            {
              unreviewed: "未审核",
              confirmed: "✓ 已确认",
              dismissed: "✗ 已驳回",
              pending: "? 待核实",
            }[it.status] || it.status;
          return (
            '<div class="' + cls + '">' +
            '<span class="p119-func">' + escHtml(it.function_id) + "</span>" +
            '<span class="p119-entity">' + escHtml(it.entity_id) + "</span>" +
            '<span class="p119-status p119-status-' + it.status + '">' + statusLabel + "</span>" +
            (it.note ? '<span class="p119-note">💬 ' + escHtml(it.note) + "</span>" : "") +
            '<span class="p119-actions">' +
            '<button data-item="' + it.id + '" data-action="confirm" class="p119-act p119-act-confirm" title="确认违规">✓</button>' +
            '<button data-item="' + it.id + '" data-action="dismiss" class="p119-act p119-act-dismiss" title="标记误报">✗</button>' +
            '<button data-item="' + it.id + '" data-action="pending" class="p119-act p119-act-pending" title="标记待核实">?</button>' +
            '<button data-item="' + it.id + '" data-action="note" class="p119-act p119-act-note" title="批注">💬</button>' +
            "</span>" +
            "</div>"
          );
        })
        .join("");
      slot.querySelectorAll(".p119-act").forEach((btn: HTMLElement) => {
        btn.onclick = () => {
          _handleAction(btn.dataset.item!, btn.dataset.action!);
        };
      });
    } catch (e) {
      console.warn("[P119Audit] 加载审核条目失败:", e);
    }
  }

  async function _handleAction(itemId: string, action: string): Promise<void> {
    try {
      if (action === "confirm") {
        await api(`/api/v1/audit/items/${encodeURIComponent(itemId)}/confirm`, {
          method: "POST",
          body: JSON.stringify({ note: "" }),
        });
        await refreshStats();
        await _refreshItems();
        (window as any).showToast?.("已确认违规", "success");
      } else if (action === "dismiss") {
        const reason = prompt("误报原因（必填）：", "实测宽度合格，图纸尺寸有误差");
        if (!reason) return;
        await api(`/api/v1/audit/items/${encodeURIComponent(itemId)}/dismiss`, {
          method: "POST",
          body: JSON.stringify({ reason }),
        });
        await refreshStats();
        await _refreshItems();
        (window as any).showToast?.("已标记误报，已自动写入反馈库", "success");
      } else if (action === "pending") {
        await api(`/api/v1/audit/items/${encodeURIComponent(itemId)}/pending`, {
          method: "POST",
          body: JSON.stringify({ note: "待现场复核" }),
        });
        await refreshStats();
        await _refreshItems();
        (window as any).showToast?.("已标记待核实", "info");
      } else if (action === "note") {
        const note = prompt("批注内容：", "");
        if (!note) return;
        await api(`/api/v1/audit/items/${encodeURIComponent(itemId)}/note`, {
          method: "PATCH",
          body: JSON.stringify({ note }),
        });
        await refreshStats();
        await _refreshItems();
        (window as any).showToast?.("批注已更新", "success");
      }
    } catch (e) {
      console.warn("[P119Audit] 操作失败:", e);
    }
  }

  // ── 对外接口 ──────────────────────────────────────────

  function init(
    containerSelector: string,
    reviewId: string,
    details?: unknown[]
  ): { refreshStats: () => Promise<void>; setReviewId: (rid: string, d?: unknown[]) => void } {
    _state.reviewId = reviewId;
    let container = document.querySelector(containerSelector) || document.getElementById("p119-audit-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "p119-audit-container";
      document.body.appendChild(container);
    }
    container.innerHTML =
      '<div id="p119-stats-bar" data-items-slot="1"></div>' +
      '<div class="p119-items-list"></div>' +
      '<div id="p119-completed-holder"></div>';

    if (details && details.length > 0) {
      api("/api/v1/audit/items", {
        method: "POST",
        body: JSON.stringify({ review_id: reviewId, details }),
      })
        .then(() => {
          _state.initialized = true;
          refreshStats();
          _refreshItems();
        })
        .catch((e) => console.warn("[P119Audit] 初始化失败:", e));
    } else {
      refreshStats().catch(() => {});
      _refreshItems();
    }
    _injectStyles();
    return { refreshStats, setReviewId };
  }

  async function setReviewId(rid: string, details?: unknown[]): Promise<void> {
    _state.reviewId = rid;
    if (details) {
      await api("/api/v1/audit/items", {
        method: "POST",
        body: JSON.stringify({ review_id: rid, details }),
      });
      await refreshStats();
      await _refreshItems();
    } else {
      await refreshStats();
      await _refreshItems();
    }
  }

  function _injectStyles(): void {
    if (document.getElementById("p119-styles")) return;
    const style = document.createElement("style");
    style.id = "p119-styles";
    style.textContent =
      ".p119-stats-row{display:flex;gap:12px;align-items:center;padding:8px 12px;background:#f8fafc;border-radius:8px;margin-bottom:12px;flex-wrap:wrap;font-size:14px}" +
      ".p119-stats-total{font-weight:600}" +
      ".p119-stat{padding:2px 8px;border-radius:12px;font-size:12px}" +
      ".p119-stat-confirmed{background:#dcfce7;color:#166534}" +
      ".p119-stat-dismissed{background:#fef3c7;color:#92400e}" +
      ".p119-stat-pending{background:#e0e7ff;color:#3730a3}" +
      ".p119-stat-unreviewed{background:#f1f5f9;color:#475569}" +
      ".p119-filter{margin-left:auto;padding:4px 8px;border-radius:6px;border:1px solid #d1d5db;font-size:13px}" +
      ".p119-item{display:flex;gap:8px;align-items:center;padding:8px;border-radius:6px;margin-bottom:4px;background:#fff;border:1px solid #e2e8f0}" +
      ".p119-item-confirmed{border-left:3px solid #22c55e}" +
      ".p119-item-dismissed{border-left:3px solid #f59e0b;opacity:0.7}" +
      ".p119-item-pending{border-left:3px solid #6366f1}" +
      ".p119-item-unreviewed{border-left:3px solid #94a3b8}" +
      ".p119-func{font-weight:600;color:#0f172a;min-width:80px}" +
      ".p119-entity{color:#475569;font-size:12px;min-width:60px}" +
      ".p119-status{color:#64748b;font-size:12px;margin-left:auto}" +
      ".p119-note{font-size:12px;color:#7c3aed;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}" +
      ".p119-actions{display:flex;gap:4px}" +
      ".p119-act{width:26px;height:26px;border:1px solid #d1d5db;border-radius:6px;background:#fff;cursor:pointer;font-size:14px}" +
      ".p119-act-confirm:hover{background:#dcfce7}" +
      ".p119-act-dismiss:hover{background:#fef3c7}" +
      ".p119-act-pending:hover{background:#e0e7ff}" +
      ".p119-act-note:hover{background:#f3e8ff}" +
      ".p119-btn-confirm{padding:6px 16px;background:#0f172a;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px}" +
      ".p119-btn-confirm:hover{background:#1e293b}" +
      ".p119-empty{text-align:center;color:#94a3b8;padding:24px;font-size:14px}";
    document.head.appendChild(style);
  }

  return { init, setReviewId, refreshStats };
})();

export { P119Audit };
(window as any).P119Audit = P119Audit;
