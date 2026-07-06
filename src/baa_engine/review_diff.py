"""审查结果对比（Diff）引擎

对比同一图纸两个版本的审查结果，输出结构化差异报告：
- 新增违规：v2 新增的违规项
- 消失违规：v1 有但 v2 已修复的违规项
- 变化违规：同一实体的值或状态发生变化
"""

from __future__ import annotations  # import

from dataclasses import dataclass, field  # dataclass support
from typing import Any, Dict, List, Optional  # typing: type hints


@dataclass  # code
class DiffItem:  # class definition
    """一条差异项"""

    diff_type: str  # "new" | "fixed" | "changed"
    clause_id: str  # code
    clause_title: str  # code
    entity_id: str  # code
    entity_type: str  # code
    old_value: Optional[float] = None  # assignment
    new_value: Optional[float] = None  # assignment
    old_required: Optional[float] = None  # assignment
    new_required: Optional[float] = None  # assignment
    old_result: str = ""  # assignment
    new_result: str = ""  # assignment
    explanation: str = ""  # assignment
    severity: str = "normal"  # "critical" | "normal" | "minor"


@dataclass  # code
class DiffReport:  # class definition
    """完整的对比报告"""

    summary: Dict[str, Any] = field(
        default_factory=lambda: {  # assignment
            "new_violations": 0,  # code
            "fixed_violations": 0,  # code
            "changed_violations": 0,  # code
            "total_v1": 0,  # code
            "total_v2": 0,  # code
        }
    )  # code
    items: List[DiffItem] = field(default_factory=list)  # function call
    v1_file: str = ""  # assignment
    v2_file: str = ""  # assignment
    v1_building_type: str = "civil"  # assignment
    v2_building_type: str = "civil"  # assignment
    v1_standard: str = "GB 50016-2014"  # assignment
    v2_standard: str = "GB 50016-2014"  # assignment


class ReviewDiffEngine:  # class definition
    """审查结果对比引擎"""

    def compare(  # function: def compare(
        self,  # code
        v1_details: List[Dict[str, Any]],  # code
        v2_details: List[Dict[str, Any]],  # code
        v1_summary: Optional[Dict[str, Any]] = None,  # assignment
        v2_summary: Optional[Dict[str, Any]] = None,  # assignment
        v1_file: str = "",  # assignment
        v2_file: str = "",  # assignment
        v1_building_type: str = "civil",  # assignment
        v2_building_type: str = "civil",  # assignment
        v1_standard: str = "GB 50016-2014",  # assignment
        v2_standard: str = "GB 50016-2014",  # assignment
    ) -> DiffReport:  # code
        """对比两个审查结果

        Args:
            v1_details: 版本1的违规详情列表
            v2_details: 版本2的违规详情列表

        Returns:
            DiffReport 包含新增、消失、变化的违规项
        """
        report = DiffReport(  # assignment
            v1_file=v1_file,  # assignment
            v2_file=v2_file,  # assignment
            v1_building_type=v1_building_type,  # assignment
            v2_building_type=v2_building_type,  # assignment
            v1_standard=v1_standard,  # assignment
            v2_standard=v2_standard,  # assignment
        )  # code

        # 构建索引： (clause_id, entity_id) -> detail
        v1_index = self._build_index(v1_details)  # function call
        v2_index = self._build_index(v2_details)  # function call

        # v1 的 key 集合
        v1_keys = set(v1_index.keys())  # function call
        v2_keys = set(v2_index.keys())  # function call

        # ── 消失违规：v1 有但 v2 没有 ────────────────────
        fixed_keys = v1_keys - v2_keys  # assignment
        for key in sorted(fixed_keys):  # loop: iterate
            v1_item = v1_index[key]  # assignment
            item = DiffItem(  # assignment
                diff_type="fixed",  # assignment
                clause_id=v1_item["clause_id"],  # assignment
                clause_title=v1_item.get("clause_title", ""),  # function call
                entity_id=v1_item["entity_id"],  # assignment
                entity_type=v1_item["entity_type"],  # assignment
                old_value=v1_item.get("extracted_value"),  # function call
                old_required=v1_item.get("required_value"),  # function call
                old_result=v1_item.get("result", "FAIL"),  # function call
                new_result="PASS",  # assignment
                explanation=v1_item.get("explanation", ""),  # function call
            )  # code
            self._set_severity(item)  # function call
            report.items.append(item)  # append to list

        # ── 新增违规：v2 有但 v1 没有 ────────────────────
        new_keys = v2_keys - v1_keys  # assignment
        for key in sorted(new_keys):  # loop: iterate
            v2_item = v2_index[key]  # assignment
            item = DiffItem(  # assignment
                diff_type="new",  # assignment
                clause_id=v2_item["clause_id"],  # assignment
                clause_title=v2_item.get("clause_title", ""),  # function call
                entity_id=v2_item["entity_id"],  # assignment
                entity_type=v2_item["entity_type"],  # assignment
                new_value=v2_item.get("extracted_value"),  # function call
                new_required=v2_item.get("required_value"),  # function call
                new_result=v2_item.get("result", "FAIL"),  # function call
                old_result="PASS",  # assignment
                explanation=v2_item.get("explanation", ""),  # function call
            )  # code
            self._set_severity(item)  # function call
            report.items.append(item)  # append to list

        # ── 变化违规：两版都有但值不同 ──────────────────
        changed_keys = v1_keys & v2_keys  # assignment
        for key in sorted(changed_keys):  # loop: iterate
            v1_item = v1_index[key]  # assignment
            v2_item = v2_index[key]  # assignment
            v1_val = v1_item.get("extracted_value")  # function call
            v2_val = v2_item.get("extracted_value")  # function call
            v1_req = v1_item.get("required_value")  # function call
            v2_req = v2_item.get("required_value")  # function call

            if v1_val != v2_val or v1_req != v2_req:  # check: OR condition
                item = DiffItem(  # assignment
                    diff_type="changed",  # assignment
                    clause_id=v2_item["clause_id"],  # assignment
                    clause_title=v2_item.get("clause_title", ""),  # function call
                    entity_id=v2_item["entity_id"],  # assignment
                    entity_type=v2_item["entity_type"],  # assignment
                    old_value=v1_val,  # assignment
                    new_value=v2_val,  # assignment
                    old_required=v1_req,  # assignment
                    new_required=v2_req,  # assignment
                    old_result=v1_item.get("result", "FAIL"),  # function call
                    new_result=v2_item.get("result", "FAIL"),  # function call
                    explanation=v2_item.get("explanation", ""),  # function call
                )  # code
                self._set_severity(item)  # function call
                report.items.append(item)  # append to list

        # ── 汇总统计 ─────────────────────────────────────
        report.summary = {  # assignment
            "new_violations": len(new_keys),  # get length
            "fixed_violations": len(fixed_keys),  # get length
            "changed_violations": len(
                [i for i in report.items if i.diff_type == "changed"]
            ),  # get length
            "total_v1": len(v1_details),  # get length
            "total_v2": len(v2_details),  # get length
        }  # code

        # 按 severity 排序：critical 优先
        severity_order = {"critical": 0, "normal": 1, "minor": 2}  # assignment
        report.items.sort(key=lambda x: severity_order.get(x.severity, 99))  # sort list

        return report  # return

    def _build_index(
        self, details: List[Dict[str, Any]]
    ) -> Dict[str, Dict]:  # function: def _build_index(self, details: List[Dict[str, Any]]) -> Dic
        """构建 (clause_id, entity_id) -> detail 索引"""
        index = {}  # assignment
        for d in details:  # loop: iterate
            key = f"{d.get('clause_id', '')}:{d.get('entity_id', '')}"  # function call
            index[key] = d  # assignment
        return index  # return

    def _set_severity(self, item: DiffItem):  # function: def _set_severity(self, item: DiffItem):
        """设置差异严重程度"""
        if item.diff_type == "new":  # condition: item.diff_type == "new":
            # 新增违规：EXIST 类比较严重，尺寸类较轻微
            if item.clause_id.startswith("EXIST"):  # condition: item.clause_id.startswith("EXIST"):
                item.severity = "critical"  # assignment
            elif item.clause_id.startswith("DIM") or item.clause_id.startswith(
                "DIST"
            ):  # elif condition
                item.severity = "normal"  # assignment
            else:  # else: default case
                item.severity = "normal"  # assignment
        elif item.diff_type == "fixed":  # elif condition
            # 修复违规：EXIST 类修复影响大
            if item.clause_id.startswith("EXIST"):  # condition: item.clause_id.startswith("EXIST"):
                item.severity = "critical"  # assignment
            else:  # else: default case
                item.severity = "normal"  # assignment
        elif item.diff_type == "changed":  # elif condition
            # 变化违规：看变化幅度
            if item.old_value and item.new_value:  # check: AND condition
                if item.old_value != 0:  # condition: item.old_value != 0:
                    ratio = abs(item.new_value - item.old_value) / abs(
                        item.old_value
                    )  # function call
                    if ratio > 0.5:  # check: numeric comparison
                        item.severity = "critical"  # assignment
                    elif ratio > 0.1:  # elif condition
                        item.severity = "normal"  # assignment
                    else:  # else: default case
                        item.severity = "minor"  # assignment
                else:  # else: default case
                    item.severity = "normal"  # assignment

    def to_json(
        self, report: DiffReport
    ) -> Dict:  # function: def to_json(self, report: DiffReport) -> Dict:
        """序列化为 JSON"""
        return {  # return: dict
            "summary": report.summary,  # code
            "v1_file": report.v1_file,  # code
            "v2_file": report.v2_file,  # code
            "v1_building_type": report.v1_building_type,  # code
            "v2_building_type": report.v2_building_type,  # code
            "v1_standard": report.v1_standard,  # code
            "v2_standard": report.v2_standard,  # code
            "items": [  # code
                {  # literal: collection
                    "diff_type": i.diff_type,  # code
                    "clause_id": i.clause_id,  # code
                    "clause_title": i.clause_title,  # code
                    "entity_id": i.entity_id,  # code
                    "entity_type": i.entity_type,  # code
                    "old_value": i.old_value,  # code
                    "new_value": i.new_value,  # code
                    "old_required": i.old_required,  # code
                    "new_required": i.new_required,  # code
                    "old_result": i.old_result,  # code
                    "new_result": i.new_result,  # code
                    "explanation": i.explanation,  # code
                    "severity": i.severity,  # code
                }  # code
                for i in report.items  # loop: iterate
            ],  # code
        }  # code
