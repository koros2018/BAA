"""审查结果对比（Diff）引擎

对比同一图纸两个版本的审查结果，输出结构化差异报告：
- 新增违规：v2 新增的违规项
- 消失违规：v1 有但 v2 已修复的违规项
- 变化违规：同一实体的值或状态发生变化
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DiffItem:
    """一条差异项"""
    diff_type: str  # "new" | "fixed" | "changed"
    clause_id: str
    clause_title: str
    entity_id: str
    entity_type: str
    old_value: Optional[float] = None
    new_value: Optional[float] = None
    old_required: Optional[float] = None
    new_required: Optional[float] = None
    old_result: str = ""
    new_result: str = ""
    explanation: str = ""
    severity: str = "normal"  # "critical" | "normal" | "minor"


@dataclass
class DiffReport:
    """完整的对比报告"""
    summary: Dict[str, Any] = field(default_factory=lambda: {
        "new_violations": 0,
        "fixed_violations": 0,
        "changed_violations": 0,
        "total_v1": 0,
        "total_v2": 0,
    })
    items: List[DiffItem] = field(default_factory=list)
    v1_file: str = ""
    v2_file: str = ""
    v1_building_type: str = "civil"
    v2_building_type: str = "civil"
    v1_standard: str = "GB 50016-2014"
    v2_standard: str = "GB 50016-2014"


class ReviewDiffEngine:
    """审查结果对比引擎"""

    def compare(
        self,
        v1_details: List[Dict[str, Any]],
        v2_details: List[Dict[str, Any]],
        v1_summary: Optional[Dict[str, Any]] = None,
        v2_summary: Optional[Dict[str, Any]] = None,
        v1_file: str = "",
        v2_file: str = "",
        v1_building_type: str = "civil",
        v2_building_type: str = "civil",
        v1_standard: str = "GB 50016-2014",
        v2_standard: str = "GB 50016-2014",
    ) -> DiffReport:
        """对比两个审查结果

        Args:
            v1_details: 版本1的违规详情列表
            v2_details: 版本2的违规详情列表

        Returns:
            DiffReport 包含新增、消失、变化的违规项
        """
        report = DiffReport(
            v1_file=v1_file,
            v2_file=v2_file,
            v1_building_type=v1_building_type,
            v2_building_type=v2_building_type,
            v1_standard=v1_standard,
            v2_standard=v2_standard,
        )

        # 构建索引： (clause_id, entity_id) -> detail
        v1_index = self._build_index(v1_details)
        v2_index = self._build_index(v2_details)

        # v1 的 key 集合
        v1_keys = set(v1_index.keys())
        v2_keys = set(v2_index.keys())

        # ── 消失违规：v1 有但 v2 没有 ────────────────────
        fixed_keys = v1_keys - v2_keys
        for key in sorted(fixed_keys):
            v1_item = v1_index[key]
            item = DiffItem(
                diff_type="fixed",
                clause_id=v1_item["clause_id"],
                clause_title=v1_item.get("clause_title", ""),
                entity_id=v1_item["entity_id"],
                entity_type=v1_item["entity_type"],
                old_value=v1_item.get("extracted_value"),
                old_required=v1_item.get("required_value"),
                old_result=v1_item.get("result", "FAIL"),
                new_result="PASS",
                explanation=v1_item.get("explanation", ""),
            )
            self._set_severity(item)
            report.items.append(item)

        # ── 新增违规：v2 有但 v1 没有 ────────────────────
        new_keys = v2_keys - v1_keys
        for key in sorted(new_keys):
            v2_item = v2_index[key]
            item = DiffItem(
                diff_type="new",
                clause_id=v2_item["clause_id"],
                clause_title=v2_item.get("clause_title", ""),
                entity_id=v2_item["entity_id"],
                entity_type=v2_item["entity_type"],
                new_value=v2_item.get("extracted_value"),
                new_required=v2_item.get("required_value"),
                new_result=v2_item.get("result", "FAIL"),
                old_result="PASS",
                explanation=v2_item.get("explanation", ""),
            )
            self._set_severity(item)
            report.items.append(item)

        # ── 变化违规：两版都有但值不同 ──────────────────
        changed_keys = v1_keys & v2_keys
        for key in sorted(changed_keys):
            v1_item = v1_index[key]
            v2_item = v2_index[key]
            v1_val = v1_item.get("extracted_value")
            v2_val = v2_item.get("extracted_value")
            v1_req = v1_item.get("required_value")
            v2_req = v2_item.get("required_value")

            if v1_val != v2_val or v1_req != v2_req:
                item = DiffItem(
                    diff_type="changed",
                    clause_id=v2_item["clause_id"],
                    clause_title=v2_item.get("clause_title", ""),
                    entity_id=v2_item["entity_id"],
                    entity_type=v2_item["entity_type"],
                    old_value=v1_val,
                    new_value=v2_val,
                    old_required=v1_req,
                    new_required=v2_req,
                    old_result=v1_item.get("result", "FAIL"),
                    new_result=v2_item.get("result", "FAIL"),
                    explanation=v2_item.get("explanation", ""),
                )
                self._set_severity(item)
                report.items.append(item)

        # ── 汇总统计 ─────────────────────────────────────
        report.summary = {
            "new_violations": len(new_keys),
            "fixed_violations": len(fixed_keys),
            "changed_violations": len([i for i in report.items if i.diff_type == "changed"]),
            "total_v1": len(v1_details),
            "total_v2": len(v2_details),
        }

        # 按 severity 排序：critical 优先
        severity_order = {"critical": 0, "normal": 1, "minor": 2}
        report.items.sort(key=lambda x: severity_order.get(x.severity, 99))

        return report

    def _build_index(self, details: List[Dict[str, Any]]) -> Dict[str, Dict]:
        """构建 (clause_id, entity_id) -> detail 索引"""
        index = {}
        for d in details:
            key = f"{d.get('clause_id', '')}:{d.get('entity_id', '')}"
            index[key] = d
        return index

    def _set_severity(self, item: DiffItem):
        """设置差异严重程度"""
        if item.diff_type == "new":
            # 新增违规：EXIST 类比较严重，尺寸类较轻微
            if item.clause_id.startswith("EXIST"):
                item.severity = "critical"
            elif item.clause_id.startswith("DIM") or item.clause_id.startswith("DIST"):
                item.severity = "normal"
            else:
                item.severity = "normal"
        elif item.diff_type == "fixed":
            # 修复违规：EXIST 类修复影响大
            if item.clause_id.startswith("EXIST"):
                item.severity = "critical"
            else:
                item.severity = "normal"
        elif item.diff_type == "changed":
            # 变化违规：看变化幅度
            if item.old_value and item.new_value:
                if item.old_value != 0:
                    ratio = abs(item.new_value - item.old_value) / abs(item.old_value)
                    if ratio > 0.5:
                        item.severity = "critical"
                    elif ratio > 0.1:
                        item.severity = "normal"
                    else:
                        item.severity = "minor"
                else:
                    item.severity = "normal"

    def to_json(self, report: DiffReport) -> Dict:
        """序列化为 JSON"""
        return {
            "summary": report.summary,
            "v1_file": report.v1_file,
            "v2_file": report.v2_file,
            "v1_building_type": report.v1_building_type,
            "v2_building_type": report.v2_building_type,
            "v1_standard": report.v1_standard,
            "v2_standard": report.v2_standard,
            "items": [
                {
                    "diff_type": i.diff_type,
                    "clause_id": i.clause_id,
                    "clause_title": i.clause_title,
                    "entity_id": i.entity_id,
                    "entity_type": i.entity_type,
                    "old_value": i.old_value,
                    "new_value": i.new_value,
                    "old_required": i.old_required,
                    "new_required": i.new_required,
                    "old_result": i.old_result,
                    "new_result": i.new_result,
                    "explanation": i.explanation,
                    "severity": i.severity,
                }
                for i in report.items
            ],
        }