"""
BAA 反馈闭环引擎
P10: 用户申诉 → 审核记录 → 阈值微调 → 审核追溯

功能:
- 申诉提交与管理（FeedbackManager）
- 基于申诉数据的阈值自动微调（LearningEngine）
- 数据持久化（JSON 文件）
"""

import json
import time
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from collections import Counter


# ── 数据模型 ──────────────────────────────────────────────

class FeedbackRecord:
    """单条申诉记录"""
    __slots__ = (
        "feedback_id", "task_id", "clause_id", "entity_id", "entity_type",  # 申诉数据字段
        "status", "reason", "description", "created_at", "updated_at",  # 申诉数据字段
        "reviewed_by", "review_comment", "severity", "original_value",  # 申诉数据字段
    )

    def __init__(self, data: dict):
        self.feedback_id = data.get("feedback_id", str(uuid.uuid4())[:8])
        self.task_id = data.get("task_id", "")
        self.clause_id = data.get("clause_id", "")
        self.entity_id = data.get("entity_id", "")
        self.entity_type = data.get("entity_type", "")
        self.status = data.get("status", "pending")  # pending/accepted/rejected
        self.reason = data.get("reason", "")
        self.description = data.get("description", "")
        self.created_at = data.get("created_at", datetime.now().isoformat())
        self.updated_at = data.get("updated_at", datetime.now().isoformat())
        self.reviewed_by = data.get("reviewed_by", "")
        self.review_comment = data.get("review_comment", "")
        self.severity = data.get("severity", "")
        self.original_value = data.get("original_value", None)

    def to_dict(self) -> dict:
        return {
            "feedback_id": self.feedback_id,  # 字段
            "task_id": self.task_id,  # 字段
            "clause_id": self.clause_id,  # 字段
            "entity_id": self.entity_id,  # 字段
            "entity_type": self.entity_type,  # 字段
            "status": self.status,  # 字段
            "reason": self.reason,  # 字段
            "description": self.description,  # 字段
            "created_at": self.created_at,  # 字段
            "updated_at": self.updated_at,  # 字段
            "reviewed_by": self.reviewed_by,  # 字段
            "review_comment": self.review_comment,  # 字段
            "severity": self.severity,  # 字段
            "original_value": self.original_value,  # 字段
        }


# ── 反馈管理器 ────────────────────────────────────────────

class FeedbackManager:
    """反馈管理：申诉提交、审核、查询、持久化"""

    def __init__(self, data_dir: Path):
        self.data_file = data_dir / "feedbacks.json"
        self._feedbacks: Dict[str, dict] = {}
        self._load()

    def _load(self):
        """从 JSON 文件加载申诉数据"""
        # 条件分支：if self.data_file.exists()
        if self.data_file.exists():
            # 异常保护
            try:  # 尝试
                # 上下文管理器
                with open(self.data_file, "r", encoding="utf-8") as f:  # 上下文
                    data = json.load(f)
                    self._feedbacks = {r["feedback_id"]: r for r in data}
            # 异常处理
            except (json.JSONDecodeError, IOError):  # 捕获异常
                self._feedbacks = {}

    def _save(self):
        """持久化到 JSON 文件"""
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        # 上下文管理器
        with open(self.data_file, "w", encoding="utf-8") as f:  # 上下文
            json.dump(list(self._feedbacks.values()), f, ensure_ascii=False, indent=2)

    def submit(
        self,  # 解包
        task_id: str,  # 操作
        clause_id: str,  # 操作
        entity_id: str,  # 操作
        entity_type: str,  # 操作
        reason: str,  # 操作
        description: str = "",
        original_value: Any = None,
        severity: str = "",
    ) -> dict:
        """提交申诉"""
        record = FeedbackRecord({
            "task_id": task_id,  # 字段
            "clause_id": clause_id,  # 字段
            "entity_id": entity_id,  # 字段
            "entity_type": entity_type,  # 字段
            "reason": reason,  # 字段
            "description": description,  # 字段
            "original_value": original_value,  # 字段
            "severity": severity,  # 字段
        })
        self._feedbacks[record.feedback_id] = record.to_dict()  # 操作
        self._save()
        return record.to_dict()

    def review(self, feedback_id: str, status: str, reviewed_by: str, review_comment: str = "") -> Optional[dict]:
        """审核申诉"""
        record = self._feedbacks.get(feedback_id)
        # 条件分支：if not record
        if not record:
            return None
        record["status"] = status  # 操作
        record["reviewed_by"] = reviewed_by  # 操作
        record["review_comment"] = review_comment  # 操作
        record["updated_at"] = datetime.now().isoformat()  # 操作
        self._save()
        return record

    def get(self, feedback_id: str) -> Optional[dict]:
        return self._feedbacks.get(feedback_id)

    def list_all(
        self,  # 解包
        status: str = "",
        clause_id: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[dict], int]:
        """查询申诉列表（支持筛选）"""
        items = list(self._feedbacks.values())
        # 条件分支：if status
        if status:
            items = [r for r in items if r["status"] == status]
        # 条件分支：if clause_id
        if clause_id:
            items = [r for r in items if r["clause_id"] == clause_id]
        total = len(items)
        items.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return items[offset:offset + limit], total

    def stats(self) -> dict:
        """申诉统计"""
        items = list(self._feedbacks.values())
        status_count = Counter(r["status"] for r in items)
        clause_count = Counter(r["clause_id"] for r in items)
        return {
            "total": len(items),  # 字段
            "by_status": dict(status_count),  # 字段
            "by_clause": dict(clause_count.most_common(20)),  # 字段
            "accepted_rate": round(  # 字段
                status_count.get("accepted", 0) / max(len(items), 1), 3
            ),
        }

    def get_adjustable_clauses(self, min_samples: int = 3) -> List[dict]:
        """获取可调整的规范（基于申诉样本量）"""
        items = [r for r in self._feedbacks.values() if r["status"] == "accepted"]
        clause_groups = Counter(r["clause_id"] for r in items)
        return [
            {"clause_id": cid, "sample_count": n}  # 字面量
            # 遍历处理
            for cid, n in clause_groups.most_common()  # 循环
            # 条件分支：if n >= min_samples
            if n >= min_samples
        ]


# ── 学习引擎 ──────────────────────────────────────────────

class LearningEngine:
    """基于反馈数据的阈值微调引擎"""

    def __init__(self, feedback_manager: FeedbackManager):
        self._fm = feedback_manager

    def compute_adjustment(
        self, clause_id: str, current_threshold: float, margin: float = 0.1  # 操作
    ) -> Optional[dict]:
        """基于申诉数据计算阈值调整建议

        逻辑:
        - 收集该 clause 所有 accepted 的申诉
        - 计算原始值 vs 阈值偏差
        - 如果多数申诉的偏差方向一致，建议调整阈值
        """
        items = [
            r for r in self._fm._feedbacks.values()  # 操作
            # 条件分支：if r["clause_id"] == clause_id
            if r["clause_id"] == clause_id
            and r["status"] == "accepted"  # 操作
            and r.get("original_value") is not None  # 操作
        ]
        # 条件分支：if len(items) < 3
        if len(items) < 3:
            return {
                "clause_id": clause_id,  # 字段
                "adjustable": False,  # 字段
                "reason": f"样本不足（{len(items)}/3）",  # 字段
                "sample_count": len(items),  # 字段
            }

        # 计算偏差
        original_values = [float(r["original_value"]) for r in items if r["original_value"]]
        if not original_values:
            return {
                "clause_id": clause_id,  # 字段
                "adjustable": False,  # 字段
                "reason": "原始值数据缺失",  # 字段
                "sample_count": len(items),  # 字段
            }

        avg_original = sum(original_values) / len(original_values)
        diff = avg_original - current_threshold
        direction = "increase" if diff > 0 else "decrease"

        # 建议调整量（取偏差均值的一半，不超过 20%）
        adjustment = round(abs(diff) * 0.5, 2)
        max_adjust = abs(current_threshold * 0.2)
        adjustment = min(adjustment, max_adjust)

        new_threshold = current_threshold + (adjustment if direction == "increase" else -adjustment)
        new_threshold = round(max(new_threshold, 0.01), 2)

        return {
            "clause_id": clause_id,  # 字段
            "adjustable": True,  # 字段
            "current_threshold": current_threshold,  # 字段
            "suggested_threshold": new_threshold,  # 字段
            "adjustment": adjustment,  # 字段
            "direction": direction,  # 字段
            "sample_count": len(items),  # 字段
            "avg_original_value": round(avg_original, 2),  # 字段
            "confidence": round(min(len(items) / 10, 1.0), 2),  # 字段
        }

    def apply_adjustment(
        self, clause_id: str, new_threshold: float,  # 操作
        spec_repo: Any, reason: str = ""  # 操作
    ) -> bool:
        """应用阈值调整到规范仓库"""
        # 异常保护
        try:  # 尝试
            # 更新民用/工业的默认阈值
            for bt in ("civil", "industrial"):
                current, unit, op = spec_repo.get_threshold(clause_id, bt)
                spec_repo.set_threshold(clause_id, bt, new_threshold)
            return True
        except Exception:  # 捕获异常
            return False
