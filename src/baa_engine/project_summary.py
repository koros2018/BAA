"""
BAA 项目级审查汇总模块
=========================
跨文件聚合审查结果，生成项目级汇总报告。

设计原则：
1. 不重新审查：从缓存读取各文件的审查结果
2. 聚合视图：按规范条目/严重级别/实体类型三个维度统计
3. 项目评分：基于加权违规扣分，支持多文件加权平均
4. 风险识别：高频违规条款自动标记为项目级风险
"""

import logging
from collections import Counter, defaultdict
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── 评分权重配置 ──────────────────────────────────────────
# severity 加权系数：critical 影响最大，minor 影响最小
SEVERITY_WEIGHTS = {
    "critical": 10.0,  # 严重：可能影响结构安全或人员疏散
    "major": 5.0,  # 较大：明显不合规但可整改
    "minor": 1.0,  # 一般：轻微偏离规范
}  # 默认扣分基数，每条违规扣除对应权重

# 项目总体评分：满分 100，扣分不超过 100
PROJECT_MAX_SCORE = 100.0
PROJECT_MIN_SCORE = 0.0

# 高频违规阈值：同一规范条目在超过此比例的文件中出现，标记为项目级风险
# 默认 30%：5 个文件中有 3 个同一条款违规 → 标记为高频
HIGH_FREQ_THRESHOLD = 0.3

# 合规率计算：通过检查数 / 总检查数
# 注意：总检查数 = 所有文件的所有 entity × clause 的组合数
COMPLIANCE_RATE_DECIMALS = 2  # 保留 2 位小数


def aggregate_project_summary(
    file_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """聚合一批文件的审查结果为项目级汇总

    输入是 batch_review 中各文件审查返回的 summary + details，
    不是原始文件内容。

    参数:
        file_results: batch_review 返回的各文件结果列表
                      每个元素包含 summary（统计）和 details（违规明细）

    返回:
        项目级汇总报告，包含：
        - overall_score: 项目总体评分（0-100）
        - compliance_rate: 合规率（0.0-1.0）
        - severity_distribution: 严重级别分布
        - clause_frequency: 规范条目违规频次（TOP 20）
        - entity_distribution: 实体类型分布
        - project_risks: 项目级风险（高频违规条款）
        - per_file_scores: 各文件评分明细
    """
    # ── 收集所有违规和统计 ─────────────────────────────────
    all_details: List[Dict] = []
    total_checks = 0
    total_violations = 0
    severity_counter = Counter()
    entity_type_counter = Counter()
    clause_counter = Counter()  # 同一规范条目跨文件的违规次数
    clause_file_set: Dict[str, set] = defaultdict(set)  # 每条 clause 涉及哪些文件
    file_scores = []

    for file_result in file_results:
        if file_result.get("status") != "success":
            # 失败的文件不计入项目评分，但保留在 per_file_scores 中
            file_scores.append(
                {
                    "filename": file_result.get("filename", "unknown"),
                    "status": file_result.get("status", "error"),
                    "score": None,
                }
            )
            continue

        summary = file_result.get("summary", {})
        details = file_result.get("details", [])

        total_checks += summary.get("total_checks", 0)
        total_violations += summary.get("violations", 0)

        # 实体类型分布
        for etype, count in summary.get("entity_types", {}).items():
            entity_type_counter[etype] += count

        # 严重级别分布
        for detail in details:
            severity = detail.get("severity", "major")
            severity_counter[severity] += 1
            clause_id = detail.get("clause_id", "unknown")
            clause_counter[clause_id] += 1

        # 收集所有违规明细（用于深度分析）
        all_details.extend(details)

        # 记录违规涉及的规范条目和文件
        filename = file_result.get("filename", "unknown")
        for detail in details:
            clause_id = detail.get("clause_id", "unknown")
            clause_file_set[clause_id].add(filename)

        # 文件评分
        file_scores.append(
            {
                "filename": filename,
                "status": "success",
                "score": summary.get("score"),
                "violations": len(details),
                "checks": summary.get("total_checks", 0),
            }
        )

    # ── 计算项目总体评分 ───────────────────────────────────
    # 方法：加权扣分法
    # score = max(0, 100 - sum(severity_weight × count) / total_files × normalization)
    # normalization：避免单文件扣分过高导致项目评分为 0
    successful_files = [fs for fs in file_scores if fs["status"] == "success"]
    num_success_files = len(successful_files)

    if num_success_files == 0 or total_checks == 0:
        overall_score = 0.0
        compliance_rate = 0.0
    else:
        # 加权扣分：critical=10, major=5, minor=1
        weighted_penalty = 0.0
        for severity, count in severity_counter.items():
            weight = SEVERITY_WEIGHTS.get(severity, 1.0)
            weighted_penalty += weight * count

        # 归一化：按文件数和检查数做加权，避免小文件项目过度扣分
        # penalty_per_check = weighted_penalty / total_checks
        # score = 100 - penalty_per_check × 100（确保满分为 100）
        if total_checks > 0:
            penalty_ratio = weighted_penalty / total_checks
            overall_score = max(0, PROJECT_MAX_SCORE - penalty_ratio * PROJECT_MAX_SCORE)
        else:
            overall_score = PROJECT_MAX_SCORE

        # 合规率 = (总检查数 - 违规数) / 总检查数
        compliance_rate = round(
            max(0, min(1, (total_checks - total_violations) / total_checks)),
            COMPLIANCE_RATE_DECIMALS,
        )

    # ── 规范条目违规频次（TOP 20） ──────────────────────────
    clause_frequency = [
        {
            "clause_id": clause_id,
            "violation_count": count,
            "files_affected": len(file_set),
        }
        for clause_id, count in clause_counter.most_common(20)
        for file_set in [clause_file_set.get(clause_id, set())]
    ]

    # ── 项目级风险识别 ──────────────────────────────────────
    # 高频违规条款：出现在超过 HIGH_FREQ_THRESHOLD 比例文件中的条款
    project_risks = []
    if num_success_files > 0:
        threshold_file_count = max(1, num_success_files * HIGH_FREQ_THRESHOLD)
        for clause_id, count in clause_counter.most_common():
            file_set = clause_file_set.get(clause_id, set())
            if len(file_set) >= threshold_file_count and count >= 2:
                # 找出该条款的平均 severity
                clause_details = [d for d in all_details if d.get("clause_id") == clause_id]
                avg_severity = _classify_overall_severity(clause_details)
                project_risks.append(
                    {
                        "clause_id": clause_id,
                        "violation_count": count,
                        "files_affected": len(file_set),
                        "severity": avg_severity,
                        "description": (
                            clause_details[0].get("clause_title", "未知条款")
                            if clause_details
                            else "未知条款"
                        ),
                    }
                )

    # ── 组装返回结果 ────────────────────────────────────────
    return {
        "overall_score": round(overall_score, 1),
        "compliance_rate": compliance_rate,
        "total_files": len(file_results),
        "successful_files": num_success_files,
        "failed_files": len(file_results) - num_success_files,
        "total_checks": total_checks,
        "total_violations": total_violations,
        "severity_distribution": dict(severity_counter),
        "entity_type_distribution": dict(entity_type_counter),
        "clause_frequency": clause_frequency[:20],
        "project_risks": project_risks,
        "per_file_scores": file_scores,
    }


def _classify_overall_severity(details: List[Dict]) -> str:
    """根据一组违规明细判断整体严重级别

    策略：取最高严重级别，如果 critical 占比超过 50% 则标记为 critical
    否则按 majority 判断
    """
    if not details:
        return "unknown"

    severity_order = {"critical": 0, "major": 1, "minor": 2}
    severity_counts = Counter(d.get("severity", "major") for d in details)
    total = len(details)

    # 最高级别
    worst = min(severity_order, key=lambda s: severity_order.get(s, 2))

    # 如果 critical 占多数，升级为 critical
    if severity_counts.get("critical", 0) / total >= 0.5:
        return "critical"

    return worst


def format_project_report(summary: Dict[str, Any]) -> str:
    """将项目汇总报告格式化为可读文本

    用于 API 返回中的 text_preview 字段，方便直接展示。
    """
    lines = [
        "=" * 50,
        "BAA 项目审查汇总报告",
        "=" * 50,
        f"项目总体评分: {summary['overall_score']}/100",
        f"合规率: {summary['compliance_rate'] * 100:.1f}%",
        f"总文件数: {summary['total_files']}（成功 {summary['successful_files']}，失败 {summary['failed_files']}）",
        f"总检查项: {summary['total_checks']}",
        f"总违规数: {summary['total_violations']}",
        "",
        "── 严重级别分布 ──",
    ]
    for severity, count in summary.get("severity_distribution", {}).items():
        lines.append(f"  {severity}: {count}")

    lines.extend(["", "── TOP 10 违规条款 ──"])
    for item in summary.get("clause_frequency", [])[:10]:
        lines.append(
            f"  {item['clause_id']}: {item['violation_count']} 次"
            f"（{item['files_affected']} 个文件）"
        )

    if summary.get("project_risks"):
        lines.extend(["", "── ⚠️ 项目级风险 ──"])
        for risk in summary["project_risks"]:
            lines.append(
                f"  {risk['clause_id']}: {risk['description']}"
                f"（{risk['violation_count']} 次违规，"
                f"{risk['files_affected']} 个文件，严重级别: {risk['severity']}）"
            )

    lines.extend(["", "=" * 50])
    return "\n".join(lines)
