"""
BAA 反馈闭环引擎
P10: 用户申诉 → 审核记录 → 阈值微调 → 审核追溯

功能:
- 申诉提交与管理（FeedbackManager）
- 基于申诉数据的阈值自动微调（LearningEngine）
- 数据持久化（JSON 文件）
"""

import json  # stdlib: JSON serialization
import uuid  # stdlib: unique ID generation
from pathlib import Path  # stdlib: filesystem path handling
from datetime import datetime  # stdlib: ISO datetime formatting
from typing import Dict, List, Optional, Any, Tuple  # typing: generic type hints
from collections import Counter  # stdlib: counter for stats

# ── 数据模型 ──────────────────────────────────────────────


class FeedbackRecord:  # definition: feedback record dataclass
    """单条申诉记录"""

    __slots__ = (  # slots: memory-efficient attribute storage
        "feedback_id",
        "task_id",
        "clause_id",
        "entity_id",
        "entity_type",  # 申诉数据字段
        "status",
        "reason",
        "description",
        "created_at",
        "updated_at",  # 申诉数据字段
        "reviewed_by",
        "review_comment",
        "severity",
        "original_value",  # 申诉数据字段
    )  # slots end

    def __init__(self, data: dict):  # constructor: create from dict
        """初始化实例。"""
        self.feedback_id = data.get(
            "feedback_id", str(uuid.uuid4())[:8]
        )  # field: unique feedback identifier
        self.task_id = data.get("task_id", "")  # field: associated task ID
        self.clause_id = data.get("clause_id", "")  # field: specification clause ID
        self.entity_id = data.get("entity_id", "")  # field: affected entity ID
        self.entity_type = data.get("entity_type", "")  # field: affected entity type
        self.status = data.get("status", "pending")  # pending/accepted/rejected
        self.reason = data.get("reason", "")  # field: reason for feedback
        self.description = data.get("description", "")  # field: detailed description
        self.created_at = data.get(
            "created_at", datetime.now().isoformat()
        )  # field: creation timestamp
        self.updated_at = data.get(
            "updated_at", datetime.now().isoformat()
        )  # field: last update timestamp
        self.reviewed_by = data.get("reviewed_by", "")  # field: reviewer identifier
        self.review_comment = data.get("review_comment", "")  # field: reviewer comment
        self.severity = data.get("severity", "")  # field: severity level
        self.original_value = data.get(
            "original_value", None
        )  # field: original value before change

    def to_dict(self) -> dict:  # method: serialize record to dict
        """序列化为字典。"""
        return {  # dict: return record as dictionary
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
        }  # dict end


# ── 反馈管理器 ────────────────────────────────────────────


class FeedbackManager:  # definition: feedback persistence manager
    """反馈管理：申诉提交、审核、查询、持久化"""

    def __init__(self, data_dir: Path):  # constructor: initialize with data directory
        """初始化实例。"""
        self.data_file = data_dir / "feedbacks.json"  # path: JSON storage file
        self._feedbacks: Dict[str, dict] = {}  # dict: in-memory feedback index
        self._load()  # call: load existing feedbacks from disk

    def _load(self):  # method: load feedbacks from JSON file
        """从 JSON 文件加载申诉数据"""
        # 条件分支：if self.data_file.exists()
        if self.data_file.exists():  # check: file must exist before reading
            # 异常保护
            try:  # 尝试
                # 上下文管理器
                with open(self.data_file, "r", encoding="utf-8") as f:  # 上下文
                    data = json.load(f)  # parse: deserialize JSON array
                    self._feedbacks = {
                        r["feedback_id"]: r for r in data
                    }  # index: build dict keyed by feedback_id
            # 异常处理
            except (json.JSONDecodeError, IOError):  # 捕获异常
                self._feedbacks = {}  # fallback: empty index on parse failure

    def _save(self):  # method: persist feedbacks to disk
        """持久化到 JSON 文件"""
        self.data_file.parent.mkdir(parents=True, exist_ok=True)  # ensure: parent directory exists
        # 上下文管理器
        with open(self.data_file, "w", encoding="utf-8") as f:  # 上下文
            json.dump(
                list(self._feedbacks.values()), f, ensure_ascii=False, indent=2
            )  # dump: write JSON array with formatting

    def submit(  # method: submit new feedback record
        self,  # 解包
        task_id: str,  # 操作
        clause_id: str,  # 操作
        entity_id: str,  # 操作
        entity_type: str,  # 操作
        reason: str,  # 操作
        description: str = "",  # param: optional description
        original_value: Any = None,  # param: original measurement value
        severity: str = "",  # param: severity classification
    ) -> dict:  # return: submitted record dict
        """提交申诉"""
        record = FeedbackRecord(
            {  # build: create FeedbackRecord from params
                "task_id": task_id,  # 字段
                "clause_id": clause_id,  # 字段
                "entity_id": entity_id,  # 字段
                "entity_type": entity_type,  # 字段
                "reason": reason,  # 字段
                "description": description,  # 字段
                "original_value": original_value,  # 字段
                "severity": severity,  # 字段
            }
        )  # build end
        self._feedbacks[record.feedback_id] = record.to_dict()  # 操作
        self._save()  # call: persist after submission
        return record.to_dict()  # return: serialized record

    def review(
        self, feedback_id: str, status: str, reviewed_by: str, review_comment: str = ""
    ) -> Optional[dict]:  # method: review and update feedback status
        """审核申诉"""
        record = self._feedbacks.get(feedback_id)  # lookup: find record by ID
        # 条件分支：if not record
        if not record:  # check: record must exist
            return None  # return: None if not found
        record["status"] = status  # 操作
        record["reviewed_by"] = reviewed_by  # 操作
        record["review_comment"] = review_comment  # 操作
        record["updated_at"] = datetime.now().isoformat()  # 操作
        self._save()  # call: persist after review
        return record  # return: updated record

    def get(self, feedback_id: str) -> Optional[dict]:  # method: get single feedback by ID
        """待补充。"""
        return self._feedbacks.get(feedback_id)  # return: record or None

    def list_all(  # method: list feedbacks with filtering
        self,  # 解包
        status: str = "",  # param: filter by status
        clause_id: str = "",  # param: filter by clause ID
        limit: int = 50,  # param: page size
        offset: int = 0,  # param: page offset
    ) -> Tuple[List[dict], int]:  # return: (items, total_count) tuple
        """查询申诉列表（支持筛选）"""
        items = list(self._feedbacks.values())  # copy: get all records as list
        # 条件分支：if status
        if status:  # filter: by status if provided
            items = [r for r in items if r["status"] == status]  # list comp: keep matching status
        # 条件分支：if clause_id
        if clause_id:  # filter: by clause ID if provided
            items = [
                r for r in items if r["clause_id"] == clause_id
            ]  # list comp: keep matching clause
        total = len(items)  # calc: total after filtering
        items.sort(
            key=lambda r: r.get("created_at", ""), reverse=True
        )  # sort: newest first by created_at
        return items[offset : offset + limit], total  # slice: return paginated subset

    def stats(self) -> dict:  # method: compute aggregate statistics
        """申诉统计"""
        items = list(self._feedbacks.values())  # copy: all feedback records
        status_count = Counter(r["status"] for r in items)  # count: status distribution
        clause_count = Counter(r["clause_id"] for r in items)  # count: clause distribution
        return {  # dict: return stats summary
            "total": len(items),  # 字段
            "by_status": dict(status_count),  # 字段
            "by_clause": dict(clause_count.most_common(20)),  # 字段
            "accepted_rate": round(  # 字段
                status_count.get("accepted", 0) / max(len(items), 1),
                3,  # calc: acceptance rate rounded to 3 decimals
            ),  # return end
        }  # dict end

    def get_adjustable_clauses(
        self, min_samples: int = 3
    ) -> List[dict]:  # method: find clauses adjustable from feedback
        """获取可调整的规范（基于申诉样本量）"""
        items = [
            r for r in self._feedbacks.values() if r["status"] == "accepted"
        ]  # filter: accepted feedbacks only
        clause_groups = Counter(
            r["clause_id"] for r in items
        )  # count: accepted feedbacks per clause
        return [  # list comp: build adjustment info
            {"clause_id": cid, "sample_count": n}  # 字面量
            # 遍历处理
            for cid, n in clause_groups.most_common()  # 循环
            # 条件分支：if n >= min_samples
            if n >= min_samples  # threshold: minimum samples required
        ]  # list end


# ── 学习引擎 ──────────────────────────────────────────────


class LearningEngine:  # definition: learning engine for threshold adjustment
    """基于反馈数据的阈值微调引擎"""

    def __init__(self, feedback_manager: FeedbackManager):  # constructor: inject feedback manager
        """初始化实例。"""
        self._fm = feedback_manager  # store: reference to FeedbackManager

    def compute_adjustment(  # method: compute recommended threshold adjustment
        self, clause_id: str, current_threshold: float, margin: float = 0.1  # 操作
    ) -> Optional[dict]:  # return: adjustment recommendation or None
        """基于申诉数据计算阈值调整建议

        逻辑:
        - 收集该 clause 所有 accepted 的申诉
        - 计算原始值 vs 阈值偏差
        - 如果多数申诉的偏差方向一致，建议调整阈值
        """
        items = [  # list comp: accepted feedbacks for clause
            r
            for r in self._fm._feedbacks.values()  # 操作
            # 条件分支：if r["clause_id"] == clause_id
            if r["clause_id"] == clause_id  # filter: match clause_id
            and r["status"] == "accepted"  # 操作
            and r.get("original_value") is not None  # 操作
        ]  # list end
        # 条件分支：if len(items) < 3
        if len(items) < 3:  # check: need minimum 3 samples
            return {  # return: insufficient data response
                "clause_id": clause_id,  # 字段
                "adjustable": False,  # 字段
                "reason": f"样本不足（{len(items)}/3）",  # 字段
                "sample_count": len(items),  # 字段
            }  # return end

        # 计算偏差
        original_values = [
            float(r["original_value"]) for r in items if r["original_value"]
        ]  # extract: numeric original values from feedbacks
        if not original_values:  # check: need valid original values
            return {  # return: no numeric data response
                "clause_id": clause_id,  # 字段
                "adjustable": False,  # 字段
                "reason": "原始值数据缺失",  # 字段
                "sample_count": len(items),  # 字段
            }  # return end

        avg_original = sum(original_values) / len(
            original_values
        )  # calc: average of original values
        diff = avg_original - current_threshold  # calc: difference between average and current
        direction = "increase" if diff > 0 else "decrease"  # calc: adjustment direction

        # 建议调整量（取偏差均值的一半，不超过 20%）
        adjustment = round(abs(diff) * 0.5, 2)  # calc: 50% of difference as adjustment
        max_adjust = abs(current_threshold * 0.2)  # cap: maximum adjustment is 20% of threshold
        adjustment = min(adjustment, max_adjust)  # clamp: limit adjustment to max

        new_threshold = current_threshold + (
            adjustment if direction == "increase" else -adjustment
        )  # apply: adjust threshold in correct direction
        new_threshold = round(max(new_threshold, 0.01), 2)  # clamp: ensure non-negative minimum

        return {  # dict: return adjustment recommendation
            "clause_id": clause_id,  # 字段
            "adjustable": True,  # 字段
            "current_threshold": current_threshold,  # 字段
            "suggested_threshold": new_threshold,  # 字段
            "adjustment": adjustment,  # 字段
            "direction": direction,  # 字段
            "sample_count": len(items),  # 字段
            "avg_original_value": round(avg_original, 2),  # 字段
            "confidence": round(min(len(items) / 10, 1.0), 2),  # 字段
        }  # dict end

    def apply_adjustment(  # method: apply threshold adjustment to spec repo
        self, clause_id: str, new_threshold: float, spec_repo: Any, reason: str = ""  # 操作  # 操作
    ) -> bool:  # return: success boolean
        """应用阈值调整到规范仓库"""
        # 异常保护
        try:  # 尝试
            # 更新民用/工业的默认阈值
            for bt in ("civil", "industrial"):  # loop: try both standard branches
                _, _, _ = spec_repo.get_threshold(clause_id, bt)  # read: current threshold config
                spec_repo.set_threshold(
                    clause_id, bt, new_threshold
                )  # write: update threshold in spec repo
            return True  # return: success
        except Exception:  # 捕获异常
            return False  # return: failure
