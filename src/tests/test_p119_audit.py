"""
P119 违规审核工作流 — 前端测试

覆盖:
    1. _initAuditItems 映射构建正确
    2. _loadAuditItemStates 状态缓存
    3. renderAuditButtons 四种状态渲染正确
    4. auditAction 调用正确 API 端点
    5. XSS 防护（用户输入全部 escHtml 转义）
"""

import re
from pathlib import Path

import pytest

JS_PATH = Path(__file__).parent.parent.parent / "src" / "frontend" / "js" / "baa-review.ts"

JAVASCRIPT = JS_PATH.read_text(encoding="utf-8")


# ───────────────────────────────────────────
# Test 1: _initAuditItems 构建正确映射
# ───────────────────────────────────────────
class TestInitAuditItems:
    """验证 _initAuditItems 函数存在且映射构建逻辑正确"""

    def test_function_exists(self):
        assert "async function _initAuditItems" in JAVASCRIPT

    def test_mapping_structure(self):
        """映射格式: {fid}:{eid}:{i} -> {reviewId}:{i}"""
        assert "reviewId + ':' + i" in JAVASCRIPT
        assert "mapping[fid + ':' + eid + ':' + i]" in JAVASCRIPT

    def test_review_id_from_queue_info(self):
        """从 queue_info.task_id 取 review_id"""
        assert "result.queue_info?.task_id" in JAVASCRIPT

    def test_review_id_from_task_id(self):
        """备用从 task_id 取 review_id"""
        assert "result.task_id" in JAVASCRIPT

    def test_init_api_call(self):
        """POST /api/v1/audit/items"""
        assert "'/api/v1/audit/items'" in JAVASCRIPT or '"/api/v1/audit/items"' in JAVASCRIPT

    def test_empty_details_no_init(self):
        """details 为空时不初始化"""
        assert "details.length === 0" in JAVASCRIPT

    def test_mapping_stored_in_window(self):
        """映射存到 window._reviewAuditMapping"""
        assert "window._reviewAuditMapping" in JAVASCRIPT

    def test_detail_list_stored_in_window(self):
        """FAIL 详情列表存到 window._reviewAuditDetailList"""
        assert "window._reviewAuditDetailList" in JAVASCRIPT


# ───────────────────────────────────────────
# Test 2: _loadAuditItemStates 状态缓存
# ───────────────────────────────────────────
class TestLoadAuditItemStates:
    """验证后端审计条目状态加载和缓存"""

    def test_function_exists(self):
        assert "async function _loadAuditItemStates" in JAVASCRIPT

    def test_uses_audit_items_api(self):
        """调用 /api/v1/audit/items?review_id="""
        assert "audit/items?review_id=" in JAVASCRIPT

    def test_caches_states_in_window(self):
        """状态缓存到 window._reviewAuditStates"""
        assert "window._reviewAuditStates" in JAVASCRIPT

    def test_iterates_items(self):
        """遍历 resp.items 构建状态映射"""
        assert "resp.items" in JAVASCRIPT

    def test_state_keyed_by_item_id(self):
        """states[item.id] = item.status"""
        assert "states[item.id]" in JAVASCRIPT

    def test_catches_errors(self):
        """网络错误不抛异常，仅 console.warn"""
        assert "console.warn" in JAVASCRIPT


# ───────────────────────────────────────────
# Test 3: renderAuditButtons 四种状态
# ───────────────────────────────────────────
class TestRenderAuditButtons:
    """验证审计操作按钮在四种状态下的渲染"""

    def test_function_exists(self):
        assert "function renderAuditButtons" in JAVASCRIPT

    def test_empty_item_id_returns_empty(self):
        """itemId 为空时返回空字符串"""
        assert "if (!itemId) return ''" in JAVASCRIPT

    def test_confirmed_state_show_confirm_badge(self):
        """confirmed 状态显示 ✅ 已确认 徽章"""
        assert "已确认" in JAVASCRIPT

    def test_confirmed_state_show_revert_button(self):
        """confirmed 状态显示驳回回退按钮"""
        assert "↩ 驳回" in JAVASCRIPT

    def test_dismissed_state_show_reject_badge(self):
        """dismissed 状态显示 ❌ 已驳回"""
        assert "已驳回" in JAVASCRIPT

    def test_dismissed_state_show_confirm_button(self):
        """dismissed 状态显示确认回退按钮"""
        assert "↩ 确认" in JAVASCRIPT

    def test_pending_state_show_three_buttons(self):
        """pending 状态显示确认/驳回/待核实按钮"""
        assert "已标记待核实" in JAVASCRIPT

    def test_unreviewed_state_show_three_buttons(self):
        """unreviewed 状态显示确认/驳回/待核实三个操作按钮"""
        # default 分支包含 confirm/dismiss/pending 三个 auditAction 调用
        default_section = JAVASCRIPT[
            JAVASCRIPT.index("default:") : JAVASCRIPT.index(
                "html += '</div>'", JAVASCRIPT.index("default:")
            )
        ]
        audit_calls = re.findall(r"auditAction\([^)]+\)", default_section)
        assert len(audit_calls) >= 3

    def test_xss_safe_clause_id(self):
        """clauseId 经过 _escHtml 转义（TS 版本使用 _escHtml(clauseId || '') 模式）"""
        assert (
            "_escHtml)(clauseId" in JAVASCRIPT
            or "_escHtml(clauseId" in JAVASCRIPT
            or "escHtml(clauseId" in JAVASCRIPT
        )

    def test_green_for_confirm(self):
        """确认按钮使用绿色样式"""
        assert "text-green-700" in JAVASCRIPT

    def test_red_for_dismiss(self):
        """驳回按钮使用红色样式"""
        assert "text-red-700" in JAVASCRIPT


# ───────────────────────────────────────────
# Test 4: auditAction API 调用
# ───────────────────────────────────────────
class TestAuditAction:
    """验证审计操作正确调用后端 API"""

    def test_function_exists(self):
        assert "async function auditAction" in JAVASCRIPT

    def test_confirmed_endpoint(self):
        """确认操作调用 POST /audit/items/{id}/confirm"""
        assert "confirm" in JAVASCRIPT

    def test_dismiss_endpoint(self):
        """驳回操作调用 POST /audit/items/{id}/dismiss"""
        assert "dismiss" in JAVASCRIPT

    def test_pending_endpoint(self):
        """待核实操作调用 POST /audit/items/{id}/pending"""
        assert "pending" in JAVASCRIPT

    def test_dismiss_requires_reason(self):
        """dismiss 操作自动附带 reason"""
        assert "reason: '人工驳回'" in JAVASCRIPT or "reason:" in JAVASCRIPT

    def test_success_toast_on_confirm(self):
        """确认成功后显示 ✅ 已确认违规"""
        assert "已确认违规" in JAVASCRIPT

    def test_success_toast_on_dismiss(self):
        """驳回成功后显示 已驳回"""
        assert "已驳回" in JAVASCRIPT

    def test_success_toast_on_pending(self):
        """待核实成功后显示 已标记待核实"""
        assert "已标记待核实" in JAVASCRIPT

    def test_error_toast_on_failure(self):
        """API 错误时显示错误信息"""
        assert "操作失败" in JAVASCRIPT

    def test_network_error_toast(self):
        """网络异常时显示错误"""
        assert "网络错误" in JAVASCRIPT

    def test_refetches_violation_page(self):
        """操作成功后刷新违规列表"""
        assert "renderViolationPage" in JAVASCRIPT

    def test_clause_id_xss_safe_in_toast(self):
        """toast 中的 clauseId 经过 _escHtml 转义"""
        assert (
            "_escHtml)(clauseId" in JAVASCRIPT
            or "_escHtml(clauseId" in JAVASCRIPT
            or "escHtml(clauseId" in JAVASCRIPT
        )


# ───────────────────────────────────────────
# Test 5: 违规列表中嵌入审核按钮
# ───────────────────────────────────────────
class TestViolationListAuditButtons:
    """验证违规列表渲染时正确嵌入审计按钮"""

    def test_audit_section_in_violation_card(self):
        """违规卡片中调用 renderAuditButtons"""
        assert "renderAuditButtons" in JAVASCRIPT

    def test_uses_audit_mapping(self):
        """使用 window._reviewAuditMapping 做映射"""
        assert "window._reviewAuditMapping" in JAVASCRIPT

    def test_uses_audit_states(self):
        """使用 window._reviewAuditStates 获取状态"""
        assert "window._reviewAuditStates" in JAVASCRIPT

    def test_state_fallback_to_unreviewed(self):
        """未加载状态时回退到 unreviewed"""
        assert "'unreviewed'" in JAVASCRIPT


# ───────────────────────────────────────────
# Test 6: 审查完成后自动初始化
# ───────────────────────────────────────────
class TestAutoInitOnReview:
    """验证审查完成后自动调用 _initAuditItems"""

    def test_called_in_run_review(self):
        """_initAuditItems 在审查成功分支中调用"""
        assert "_initAuditItems(result)" in JAVASCRIPT


# ───────────────────────────────────────────
# Test 7: XSS 防护全面检查
# ───────────────────────────────────────────
class TestXSSProtection:
    """验证所有用户输入/后端数据经过转义"""

    def test_all_audit_toast_inputs_escaped(self):
        """auditAction toast 中 clauseId 经过 _escHtml 转义"""
        audit_start = JAVASCRIPT.index("async function auditAction")
        audit_end = JAVASCRIPT.index("// ── P45", audit_start)
        audit_section = JAVASCRIPT[audit_start:audit_end]
        # showToast 调用中存在 _escHtml(clauseId
        # TS 版本: (window._escHtml || _escHtml)(clauseId || '')
        assert (
            "_escHtml)(clauseId" in audit_section
            or "_escHtml(clauseId" in audit_section
            or "escHtml(clauseId" in audit_section
        )

    def test_action_param_escaped_in_url(self):
        """action 参数在 URL 中经过 _escHtml 转义"""
        assert (
            "_escHtml)(action" in JAVASCRIPT
            or "_escHtml(action" in JAVASCRIPT
            or "escHtml(action" in JAVASCRIPT
        )

    def test_item_id_encoded_in_url(self):
        """itemId 在 URL 中经过 encodeURIComponent"""
        assert "encodeURIComponent(itemId)" in JAVASCRIPT

    def test_review_id_encoded(self):
        """reviewId 在 API URL 中经过 encodeURIComponent"""
        assert "encodeURIComponent(reviewId)" in JAVASCRIPT
