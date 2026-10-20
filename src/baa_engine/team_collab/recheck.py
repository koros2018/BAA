"""BAA 协作模块 — 复查引擎（T-B6 工作流闭环）

复查 = 对审查会话 file_ids 复跑规范审查，与上次快照（ReviewSession.result_summary.details）
做 findings 对比（resolved/new/persisted），并经状态机流转到 rechecking。

复跑内核与 /review 的 _do_clustering 同构（链式非全局函数 + P70 全局 exist +
T-B2 作用域聚合 exist 缺失），保证复查口径与审查一致。

对比口径：finding 键 = (clause_id, entity_id, func_id)，重复条目折叠。
- resolved：旧有新无（已整改）
- new：旧无新有（新增/复发）
- persisted：两侧均有（未修复）
"""

import logging

import time

from typing import List, Optional, Tuple


from .manager import CollaborationManager, _check_permission

from .models import ProjectPermission, ReviewSession, ReviewStatus, REVIEW_STATUS_TRANSITIONS


logger = logging.getLogger(__name__)


def _finding_key(d: dict) -> tuple:
    """finding 对比键。"""
    return (d.get("clause_id", ""), d.get("entity_id", ""), d.get("func_id", ""))


def _brief(d: dict) -> dict:
    """finding 摘要（对比明细用）。"""
    return {
        "clause_id": d.get("clause_id", ""),
        "clause_title": d.get("clause_title", ""),
        "entity_id": d.get("entity_id", ""),
        "entity_type": d.get("entity_type", ""),
        "func_id": d.get("func_id", ""),
        "severity": d.get("severity", ""),
        "explanation": (d.get("explanation") or "")[:120],
    }


def compare_findings(old_details: List[dict], new_details: List[dict]) -> dict:
    """新旧 findings 集合对比：resolved/new/persisted 计数 + 明细。"""
    old_map = {}
    for d in old_details or []:
        old_map.setdefault(_finding_key(d), _brief(d))
    new_map = {}
    for d in new_details or []:
        new_map.setdefault(_finding_key(d), _brief(d))
    old_keys, new_keys = set(old_map), set(new_map)

    def _items(keys, src):
        return [src[k] for k in sorted(keys)]

    return {
        "resolved": {"count": len(old_keys - new_keys), "items": _items(old_keys - new_keys, old_map)},
        "new": {"count": len(new_keys - old_keys), "items": _items(new_keys - old_keys, new_map)},
        "persisted": {"count": len(old_keys & new_keys), "items": _items(old_keys & new_keys, new_map)},
    }


def run_findings_for_file(file_id: str, building_type: str = "civil") -> List[dict]:
    """对已上传文件复跑规范审查，返回与 /review details 同构的 findings 列表。

    内核与 review_routes._do_clustering 同构；同步阻塞调用，路由层应放线程池。
    """
    from src.api.api_globals import get_file_path

    file_path = get_file_path(file_id)

    if not file_path:

        raise FileNotFoundError(f"文件不存在: {file_id}")

    from src.api.review import _get_aa, _get_dp, _get_fr, _get_sa
    from src.api.review._shared import _confidence_tier
    from src.baa_engine.scope_aggregator import aggregate_exist_in_scopes, build_scopes
    from src.baa_engine.spec_repository import SpecRepository

    parse_result = _get_dp().parse(str(file_path), file_id)

    if not getattr(parse_result, "success", True):

        raise ValueError(f"图纸解析失败: {getattr(parse_result, 'error', '未知错误')}")

    semantic = _get_sa().analyze(
        parse_result.primitives, parse_result.dimensions, building_type=building_type
    )

    entities = semantic["entities"]

    fr = _get_fr()

    repo = SpecRepository()

    effective_types = [building_type]

    def get_strict_threshold(clause_id: str) -> tuple:
        """获取条款严格模式阈值。"""
        worst_val, worst_unit, worst_op = None, None, None
        for bt in effective_types:
            v, u, o = repo.get_threshold(clause_id, bt)
            if worst_val is None or v > worst_val:
                worst_val, worst_unit, worst_op = v, u, o
        return worst_val, worst_unit, worst_op

    details: List[dict] = []

    registry_funcs = fr.list_all()

    func_ids = [
        f.func_id for f in registry_funcs if not getattr(f, "requires_global_context", False)
    ]

    global_funcs = [f for f in registry_funcs if getattr(f, "requires_global_context", False)]

    for e in entities:

        chained_results = fr.execute_chained(func_ids, e)

        for fid, r in chained_results.items():

            func = fr.get(fid)

            if func is None or r is None:

                continue

            if r.result == "PASS":

                continue

            clause = {
                "standard": "GB50016",
                "clause_id": func.clause_id,
                "title": func.name,
                "text": func.description,
                "category": func.category.value,
            }

            f = _get_aa().build_finding(r, clause, e, entities[:5])

            details.append(
                {
                    "entity_id": e.get("id", e.get("type", "")),
                    "entity_type": e["type"],
                    "clause_id": f.clause.get("clause_id", ""),
                    "clause_title": f.clause.get("title", ""),
                    "func_id": func.func_id,
                    "result": f.judgement["result"],
                    "extracted_value": f.extracted_params["extracted_value"],
                    "required_value": f.extracted_params.get("required_value", 1.2),
                    "difference": f.extracted_params.get("difference", 0),
                    "severity": f.judgement.get("severity", "major"),
                    "explanation": f.explanation[:120],
                    "confidence": r.confidence,
                    "confidence_tier": _confidence_tier(r.confidence),
                }
            )

    # P70: requires_global_context 函数全局聚合判定
    for func in global_funcs:

        if func.category.value != "exist":

            continue

        func_targets = set(func.target_entities) if func.target_entities else set()

        if not func_targets:

            continue

        matching = [e for e in entities if e.get("type", "") in func_targets]

        if not matching:

            continue

        count = len(matching)

        if count < func.threshold:

            details.append(
                {
                    "entity_id": "",
                    "entity_type": ",".join(func_targets),
                    "clause_id": func.clause_id,
                    "clause_title": func.name,
                    "func_id": func.func_id,
                    "result": "FAIL",
                    "extracted_value": float(count),
                    "required_value": float(func.threshold),
                    "difference": float(count - func.threshold),
                    "explanation": f"全局共检出{count}个，要求≥{func.threshold}",
                    "severity": "critical",
                    "confidence": 1.0,
                    "confidence_tier": "confirmed",
                }
            )

    # T-B2: EXIST-* 作用域聚合缺失检查（与 /review 同口径）
    entity_types_in_drawing = set(e.get("type", "") for e in entities)

    for func in registry_funcs:

        if func.category.value != "exist":

            continue

        func_targets = set(func.target_entities) if func.target_entities else set()

        if func_targets and not func_targets.intersection(entity_types_in_drawing):

            continue

        scope_info = ""

        severity = "critical"

        if func_targets:

            sc = build_scopes(entities)

            agg = aggregate_exist_in_scopes(func.func_id, list(func_targets), entities, sc)

            if agg["overall"] == "pass":

                continue

            if agg["overall"] == "partial":

                severity = "low"

                scope_info = (
                    f"；以下区域未检出({len(agg['missing_scopes'])}"
                    f"/{len(agg['scope_results'])} 个作用域)"
                )

            has_match = False

        else:

            has_match = any(func.matches(e) for e in entities)

        if not has_match:

            r = fr.execute_with_timeout(func, None)

            if r is not None and r.result != "PASS":

                clause = {
                    "standard": "GB50016",
                    "clause_id": func.clause_id,
                    "title": func.name,
                    "text": func.description,
                    "category": func.category.value,
                }

                f = _get_aa().build_finding(r, clause, {}, entities[:5])

                details.append(
                    {
                        "entity_id": "",
                        "entity_type": "missing",
                        "clause_id": f.clause.get("clause_id", ""),
                        "clause_title": f.clause.get("title", ""),
                        "func_id": func.func_id,
                        "result": f.judgement["result"],
                        "extracted_value": 0.0,
                        "required_value": f.extracted_params.get("required_value", 1.0),
                        "difference": -f.extracted_params.get("required_value", 1.0),
                        "explanation": (f.explanation + scope_info)[:160],
                        "severity": severity,
                        "confidence": r.confidence,
                        "confidence_tier": _confidence_tier(r.confidence),
                    }
                )

    return details


def recheck_session(
    mgr: CollaborationManager,
    session_id: str,
    user_id: str,
    building_type: str = "civil",
) -> Tuple[Optional[dict], str]:
    """复查：复跑会话 file_ids 审查并与快照对比；状态经状态机流转到 rechecking。

    返回 ({"comparison":…, "findings_count":…, "errors":[…]}, msg)。
    """
    db = mgr._get_session()

    try:

        rs = db.query(ReviewSession).filter(ReviewSession.id == session_id).first()

        if not rs:

            return None, "会话不存在"

        perm = mgr._get_project_permission(db, rs.project_id, user_id)

        if not _check_permission(perm, ProjectPermission.EDIT.value):

            return None, "无权限"

        # 先校验状态流转合法性（rectifying→rechecking 等），避免白跑审查
        if ReviewStatus.RECHECKING.value not in REVIEW_STATUS_TRANSITIONS.get(rs.status, set()):

            return None, f"非法状态流转: {rs.status} -> {ReviewStatus.RECHECKING.value}"

        file_ids = list(rs.file_ids or [])

        if not file_ids:

            return None, "会话未关联图纸文件"

        old_summary = rs.result_summary if isinstance(rs.result_summary, dict) else {}

        old_details = old_summary.get("details", []) if isinstance(old_summary, dict) else []

        new_details: List[dict] = []

        errors: List[str] = []

        for fid in file_ids:

            try:

                new_details.extend(run_findings_for_file(fid, building_type))

            except Exception as e:

                errors.append(f"{fid}: {e}")

        if errors and not new_details:

            return None, "复查失败: " + "; ".join(errors)

        comparison = compare_findings(old_details, new_details)

        rs.result_summary = {
            "details": new_details,
            "last_compare": comparison,
            "rechecked_at": time.time(),
            "rechecked_by": user_id,
        }

        db.commit()

        ok, msg = mgr.update_review_session_status(
            session_id, user_id, ReviewStatus.RECHECKING.value
        )

        if not ok:

            return None, f"复查失败: {msg}"

        logger.info(f"[Collab] 复查完成: {session_id} 新{comparison['new']['count']} "
                    f"解决{comparison['resolved']['count']} 持存{comparison['persisted']['count']}")

        return {
            "comparison": comparison,
            "findings_count": len(new_details),
            "errors": errors,
        }, "success"

    except Exception as e:

        db.rollback()

        return None, str(e)

    finally:

        mgr._close_session(db)
