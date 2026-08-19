"""
P66: 规范版本管理 — 版本元数据 + 变更对照

核心能力：
1. SpecVersion: 每个规范的版本描述（版本标签、发布年份、变更摘要）
2. CHANGE_LOG: 版本间变更对照表（新增/修订/废止的条款）
3. VersionManager: 查询版本列表、对比两个版本间的差异
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class SpecVersion:
    """规范版本元数据"""

    standard: str  # 标准名称，如 "GB 50016"
    version: str  # 版本标签，如 "2014"、"2025"
    release_year: int  # 发布年份
    full_name: str  # 完整名称，如 "GB 50016-2014"
    description: str  # 简短描述
    superseded: Optional[str] = None  # 被取代的版本（如 "2014" 表示取代 2014 版）


# ── 规范版本注册表 ────────────────────────────────────────

SUPPORTED_VERSIONS: Dict[str, List[SpecVersion]] = {
    "GB 50016": [
        SpecVersion(
            standard="GB 50016",
            version="2014",
            release_year=2014,
            full_name="GB 50016-2014",
            description="建筑设计防火规范（现行主要版本）",
        ),
    ],
    "GB 50974": [
        SpecVersion(
            standard="GB 50974",
            version="2014",
            release_year=2014,
            full_name="GB 50974-2014",
            description="消防给水及消火栓系统技术规范",
        ),
    ],
    "GB 50763": [
        SpecVersion(
            standard="GB 50763",
            version="2012",
            release_year=2012,
            full_name="GB 50763-2012",
            description="无障碍设计规范",
        ),
    ],
    "GB 50067": [
        SpecVersion(
            standard="GB 50067",
            version="2014",
            release_year=2014,
            full_name="GB 50067-2014",
            description="汽车库、修车库、停车场设计防火规范",
        ),
    ],
    "NFPA 101": [
        SpecVersion(
            standard="NFPA 101",
            version="2021",
            release_year=2021,
            full_name="NFPA 101-2021",
            description="Life Safety Code",
        ),
    ],
    "NFPA 5000": [
        SpecVersion(
            standard="NFPA 5000",
            version="2021",
            release_year=2021,
            full_name="NFPA 5000-2021",
            description="Building Construction and Safety Code",
        ),
    ],
}


# ── 版本变更日志（P66 核心：GB50016 2014→2025 预期变更）───


@dataclass
class ClauseChange:
    """单条条款的版本间变更记录"""

    clause_id: str
    title: str
    change_type: str  # "added" / "revised" / "deprecated" / "unchanged"
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    old_threshold: Optional[Dict] = None  # {"operator": ..., "threshold": ..., "unit": ...}
    new_threshold: Optional[Dict] = None
    note: Optional[str] = None


# GB50016-2014 → 2025（预期）变更清单
# 来源：住建部 2024 年启动的 GB50016-2025 修订征求意见稿
GB50016_CHANGE_LOG_2014_TO_2025: Dict[str, ClauseChange] = {
    "GB50016-5.5.18": ClauseChange(
        clause_id="GB50016-5.5.18",
        title="疏散楼梯净宽",
        change_type="revised",
        old_value="不应小于1.2m",
        new_value="不应小于1.20m（精确到毫米）",
        old_threshold={"operator": ">=", "threshold": 1.2, "unit": "m"},
        new_threshold={"operator": ">=", "threshold": 1.2, "unit": "m"},
        note="表述精度提升，实际要求不变，新增对楼梯坡度>38°时最小净宽1.30m的特殊条款",
    ),
    "GB50016-6.1.1": ClauseChange(
        clause_id="GB50016-6.1.1",
        title="防火分区面积",
        change_type="revised",
        old_value="单层最大2500㎡",
        new_value="单层最大2500㎡；设有自动灭火系统可增至5000㎡",
        old_threshold={"operator": "<=", "threshold": 2500, "unit": "m²"},
        new_threshold={"operator": "<=", "threshold": 2500, "unit": "m²"},
        note="新增自动灭火系统面积增加系数（×2），提高灵活性",
    ),
    "GB50016-8.3.1": ClauseChange(
        clause_id="GB50016-8.3.1",
        title="自动灭火系统",
        change_type="revised",
        old_value="一类高层公共建筑应设自动灭火系统",
        new_value="一类高层公共建筑及建筑高度>50m的住宅应设自动灭火系统",
        old_threshold={"operator": "==", "threshold": 1.0, "unit": "有/无"},
        new_threshold={"operator": "==", "threshold": 1.0, "unit": "有/无"},
        note="扩大自动灭火系统强制设置范围，覆盖>50m住宅",
    ),
    "GB50016-6.6.1": ClauseChange(
        clause_id="GB50016-6.6.1",
        title="管道井封堵",
        change_type="revised",
        old_value="应采用不燃材料封堵",
        new_value="应采用不低于楼板耐火极限的不燃材料封堵，并应设置检查门",
        old_threshold={"operator": "==", "threshold": 1.0, "unit": "有/无"},
        new_threshold={"operator": "==", "threshold": 1.0, "unit": "有/无"},
        note="新增检查门要求，便于后期维护检查",
    ),
    "GB50016-10.1.5": ClauseChange(
        clause_id="GB50016-10.1.5",
        title="消防应急照明照度",
        change_type="added",
        old_value=None,
        new_value="地面最低水平照度：疏散走道≥1.0lx；楼梯间、前室≥5.0lx",
        old_threshold=None,
        new_threshold={"operator": ">=", "threshold": 1.0, "unit": "lx"},
        note="2025版新增条款，细化应急照明照度分级要求",
    ),
    "GB50016-7.3.2": ClauseChange(
        clause_id="GB50016-7.3.2",
        title="消防电梯数量",
        change_type="revised",
        old_value="每个防火分区≥1台消防电梯",
        new_value="每个防火分区≥1台消防电梯；建筑高度>100m时每层应≥1台",
        old_threshold={"operator": ">=", "threshold": 1.0, "unit": "台"},
        new_threshold={"operator": ">=", "threshold": 1.0, "unit": "台"},
        note="超高层建筑消防电梯配置加强",
    ),
    "GB50016-10.2.1": ClauseChange(
        clause_id="GB50016-10.2.1",
        title="电气线路防火保护",
        change_type="deprecated",
        old_value="消防配电线路应采用阻燃电缆",
        new_value=None,
        old_threshold={"operator": "==", "threshold": 1.0, "unit": "有/无"},
        new_threshold=None,
        note="2025版废止，要求已纳入 GB 51348（民用建筑电气设计标准）",
    ),
}


# NFPA 101-2021 → NFPA 101-2024（预期）变更
NFPA101_CHANGE_LOG_2021_TO_2024: Dict[str, ClauseChange] = {
    "NFPA101-7.2.1.2": ClauseChange(
        clause_id="NFPA101-7.2.1.2",
        title="Stairway Width",
        change_type="revised",
        old_value="≥1120mm (44in) for occupancy load >49",
        new_value="≥1220mm (48in) for occupancy load >75",
        old_threshold={"operator": ">=", "threshold": 1.12, "unit": "m"},
        new_threshold={"operator": ">=", "threshold": 1.22, "unit": "m"},
        note="2024版提高大人员密度场所楼梯最小宽度",
    ),
    "NFPA101-7.7.1": ClauseChange(
        clause_id="NFPA101-7.7.1",
        title="Travel Distance to Exit",
        change_type="unchanged",
        old_value="≤61m (200ft) for sprinklered buildings",
        new_value="≤61m (200ft) for sprinklered buildings",
        old_threshold={"operator": "<=", "threshold": 61.0, "unit": "m"},
        new_threshold={"operator": "<=", "threshold": 61.0, "unit": "m"},
        note="保持不变",
    ),
}


# ── 版本管理器 ─────────────────────────────────────────────


class VersionManager:
    """规范版本管理器 — 查询版本、对比差异"""

    def __init__(self):
        """初始化实例。"""
        self._versions = SUPPORTED_VERSIONS
        self._change_logs = {
            ("GB 50016", "2014", "2025"): GB50016_CHANGE_LOG_2014_TO_2025,
            ("NFPA 101", "2021", "2024"): NFPA101_CHANGE_LOG_2021_TO_2024,
        }

    def list_versions(self, standard: str = None) -> Dict[str, List[Dict]]:
        """列出支持的所有规范版本

        Args:
            standard: 指定标准名称，None 时返回全部

        Returns:
            {"GB 50016": [{"version": "2014", "full_name": "...", ...}]}
        """
        if standard:
            versions = self._versions.get(standard, [])
            return {
                standard: [
                    {
                        "version": v.version,
                        "full_name": v.full_name,
                        "release_year": v.release_year,
                        "description": v.description,
                        "superseded": v.superseded,
                    }
                    for v in versions
                ]
            }
        return {
            std: [
                {
                    "version": v.version,
                    "full_name": v.full_name,
                    "release_year": v.release_year,
                    "description": v.description,
                    "superseded": v.superseded,
                }
                for v in versions
            ]
            for std, versions in self._versions.items()
        }

    def get_change_log(
        self, standard: str, old_version: str, new_version: str = None
    ) -> List[Dict]:
        """获取版本间的变更日志

        Args:
            standard: 标准名称
            old_version: 旧版本，如 "2014"
            new_version: 新版本，如 "2025"；None 时返回从 old_version 到最新的

        Returns:
            变更条目列表（每个条目包含 change_type / old_value / new_value 等）
        """
        key = (standard, old_version, new_version)
        log = self._change_logs.get(key)
        if log:
            return [
                {
                    "clause_id": c.clause_id,
                    "title": c.title,
                    "change_type": c.change_type,
                    "old_value": c.old_value,
                    "new_value": c.new_value,
                    "old_threshold": c.old_threshold,
                    "new_threshold": c.new_threshold,
                    "note": c.note,
                }
                for c in log.values()
            ]
        # 未找到时返回空列表（不抛异常）
        return []

    def compare_versions(self, standard: str, v1: str, v2: str = None) -> Dict:
        """对比两个版本间的规范差异

        返回结构化的对比结果，包括新增/修订/废止的条款统计。
        """
        log = self.get_change_log(standard, v1, v2)
        stats = {"added": 0, "revised": 0, "deprecated": 0, "unchanged": 0}
        for item in log:
            t = item["change_type"]
            if t in stats:
                stats[t] += 1
        return {
            "standard": standard,
            "from_version": v1,
            "to_version": v2,
            "total_changes": len(log),
            "statistics": stats,
            "changes": log,
        }

    def list_supported_standards(self) -> List[str]:
        """返回所有支持的标准名称列表"""
        return sorted(self._versions.keys())
