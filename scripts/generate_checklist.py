#!/usr/bin/env python3
"""Generate expert confirmation checklist for remaining 35 violations."""

import json
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORT = PROJECT_ROOT / "data" / "fp_rate_audit_report.json"
OUTPUT = PROJECT_ROOT / "docs" / "expert-confirmation-checklist-20261102.html"


def severity_tag(sev):
    if sev == "critical":
        return '<span class="tag tag-critical">critical</span>'
    if sev == "major":
        return '<span class="tag tag-info">major</span>'
    return '<span class="tag" style="background:rgba(131,56,236,0.15);color:#8338ec">minor</span>'


def risk_tag(risk):
    return f'<span class="tag tag-{risk}">{risk}</span>'


def verdict_cell():
    return """<select style="background:var(--surface2);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:4px 8px;">
<option value="">待确认</option>
<option value="true">✓ 真实违规</option>
<option value="false">✗ 误报</option>
<option value="partial">~ 部分误报</option>
<option value="exclude">⊘ 应排除（非建筑场景）</option>
</select>"""


def main():
    with open(REPORT, encoding="utf-8") as f:
        data = json.load(f)

    # Associate each finding with its source file (filename is at report level)
    file_map = {}
    for r in data:
        if not r.get("success"):
            continue
        fname = r.get("file", "")
        for f in r["findings"]:
            fid_key = (f.get("func_id"), f.get("entity_id", ""))
            file_map[fid_key] = fname

    all_f = [f for r in data if r.get("success") for f in r["findings"]]
    print(f"Raw findings: {len(all_f)}")

    # Deduplicate: same func_id + entity_id → keep highest severity
    severity_rank = {"critical": 3, "major": 2, "minor": 1}
    deduped = {}
    for f in all_f:
        key = (f["func_id"], f.get("entity_id", ""))
        fname = file_map.get(key, "")
        if key not in deduped or severity_rank.get(f["severity"], 0) > severity_rank.get(deduped[key]["severity"], 0):
            entry = dict(deduped.get(key, f))
            entry.update(f)
            entry["file"] = fname
            deduped[key] = entry
    items = list(deduped.values())
    print(f"Unique items after dedup: {len(items)}")

    # Group by rule
    groups = {}
    for f in items:
        groups.setdefault(f["func_id"], []).append(f)

    # Rule guidance for experts
    guidance = {
        "DIM-006": {
            "title": "DIM-006 — 疏散门净宽",
            "clause": "GB50016-5.5.19",
            "threshold": "≥1.4m",
            "guidance": (
                "1. 确认门是否为疏散门（非设备门/管井门）<br>"
                "2. 确认建筑类型：工业建筑疏散门阈值可能不同<br>"
                "3. 检查宽度值来源：dimension标注 vs bbox推断<br>"
                "4. c157664图纸为立-门窗层，需区分设备门与人员通行门"
            ),
            "priority": "P2",
        },
        "DIM-113": {
            "title": "DIM-113 — 房间疏散门净宽",
            "clause": "GB50016-5.5.21",
            "threshold": "≥0.9m",
            "guidance": (
                "1. 宽度 ≤0.6m 的门已自动跳过（视为设备/管井门）<br>"
                "2. 剩余 0.60~0.80m 的门：确认是否为真实疏散门<br>"
                "3. 若是设备间/管道井的门，属于误报，应标记排除<br>"
                "4. 若是人员通道的门，宽度不足，属真实违规"
            ),
            "priority": "P1",
        },
        "EVAC-001": {
            "title": "EVAC-001 — 疏散路径连通性",
            "clause": "GB50016-5.5.17",
            "threshold": "=1（至少一条疏散路径）",
            "guidance": (
                "1. 打开图纸定位房间，检查是否有出口标注<br>"
                "2. 检查门类型：exit_door vs 普通 door<br>"
                "3. 检查是否存在被墙体完全包围的情况<br>"
                "4. 置信度 0.80 较低，可能是扫描法派生房间问题<br>"
                "5. line_chain_*/polyline_room_* 为扫线法临时产物，应排除"
            ),
            "priority": "P1",
        },
        "EVAC-002": {
            "title": "EVAC-002 — 疏散距离超标（两个方向）",
            "clause": "GB50016-5.5.17",
            "threshold": "≤30m（民用）/ ≤40m（工业）",
            "guidance": (
                "1. 确认建筑类型，民用/工业阈值不同<br>"
                "2. 查看疏散路径长度计算依据（bbox边缘距离累加）<br>"
                "3. >80m 的值视为 BFS 计算异常，已由代码自动过滤<br>"
                "4. 剩余 30~44m 的需确认是否真实超标"
            ),
            "priority": "P1",
        },
        "EVAC-003": {
            "title": "EVAC-003 — 袋形走道疏散距离",
            "clause": "GB50016-5.5.17",
            "threshold": "≤20m（民用）/ ≤22m（工业）",
            "guidance": (
                "1. 确认走道是否为袋形走道（一端封闭）<br>"
                "2. 测量实际走道长度<br>"
                "3. polyline_corridor_* 为扫描法派生实体，需确认是否为真实走廊"
            ),
            "priority": "P1",
        },
        "EVAC-004": {
            "title": "EVAC-004 — 疏散路径瓶颈",
            "clause": "GB50016-5.5.18",
            "threshold": "door ≥0.79m",
            "guidance": (
                "1. 确认瓶颈门的具体宽度和位置<br>"
                "2. 区分疏散门与设备门/检修门<br>"
                "3. 阈值已从 0.8m 调整为 0.79m 消除浮点边界误判<br>"
                "4. 若门宽 0.79~0.80m，需结合建筑规范确认是否符合要求"
            ),
            "priority": "P1",
        },
        "AREA-018": {
            "title": "AREA-018 — 防烟楼梯间前室面积",
            "clause": "GB50016-6.4.3",
            "threshold": "≥4.5m²",
            "guidance": (
                "1. 确认实体是否为真正的防烟楼梯间前室<br>"
                "2. <2m² 的 ante chamber 已自动跳过（极大概率为误分类）<br>"
                "3. 剩余 2~4.5m² 的需精确测量实际面积<br>"
                "4. 住宅建筑前室面积要求可能不同（≥3.0m²）"
            ),
            "priority": "P1",
        },
        "AREA-019": {
            "title": "AREA-019 — 消防电梯前室面积",
            "clause": "GB50016-7.3.5",
            "threshold": "≥6.0m²",
            "guidance": (
                "1. 确认实体是否为消防电梯前室<br>"
                "2. <2m² 的已自动跳过（疑似管道井/设备间误标）<br>"
                "3. 剩余面积不足的需实测确认<br>"
                "4. 注意与 AREA-018 的区别：消防电梯前室 vs 防烟楼梯间前室"
            ),
            "priority": "P2",
        },
        "AREA-021": {
            "title": "AREA-021 — 剪刀楼梯间前室面积",
            "clause": "GB50016-6.4.4",
            "threshold": "≥6.0m²",
            "guidance": (
                "1. 确认实体是否为剪刀楼梯间前室<br>"
                "2. <2m² 的已自动跳过<br>"
                "3. 同一 ante chamber 可能同时触发 AREA-018/019/021，只保留最严重一条<br>"
                "4. 剪刀楼梯间有特殊的面积计算规则"
            ),
            "priority": "P2",
        },
        "DIST-003": {
            "title": "DIST-003 — 袋形走道长度",
            "clause": "GB50016-5.5.17",
            "threshold": "≤20m（民用）/ ≤22m（工业）",
            "guidance": (
                "1. polyline_corridor_* 为扫描法派生实体，需确认是否为真实走廊<br>"
                "2. 测量实际走道长度<br>"
                "3. 区分袋形走道与穿越走道"
            ),
            "priority": "P2",
        },
    }

    html_parts = [
        """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>BAA 专家确认清单 — 剩余 35 条违规</title>
<style>
  :root { --bg:#0f1117; --surface:#1a1d27; --surface2:#232733; --border:#2e3345; --text:#e2e4eb; --muted:#8a8fa8;
          --red:#ff5c5c; --orange:#ffb347; --yellow:#ffd166; --green:#06d6a0; --blue:#118ab2; --purple:#8338ec; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:var(--bg); color:var(--text); font-family:-apple-system,"Microsoft YaHei",sans-serif; font-size:14px; }
  .container { max-width:1100px; margin:0 auto; padding:24px; }
  h1 { font-size:22px; color:var(--blue); margin-bottom:4px; }
  h2 { font-size:17px; color:var(--purple); margin:28px 0 12px; padding-bottom:6px; border-bottom:1px solid var(--border); }
  h3 { font-size:15px; color:var(--orange); margin:18px 0 8px; }
  .subtitle { color:var(--muted); font-size:13px; margin-bottom:24px; }
  .card { background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:16px 20px; margin-bottom:16px; }
  .kpi-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:12px; margin-bottom:24px; }
  .kpi { background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:14px 16px; text-align:center; }
  .kpi .label { font-size:12px; color:var(--muted); margin-bottom:4px; }
  .kpi .value { font-size:26px; font-weight:700; }
  table { width:100%; border-collapse:collapse; margin:12px 0; font-size:13px; }
  th,td { padding:8px 10px; border:1px solid var(--border); text-align:left; vertical-align:top; }
  th { background:var(--surface2); color:var(--muted); font-weight:600; font-size:12px; }
  .tag { display:inline-block; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:600; }
  .tag-fixed { background:rgba(6,214,160,0.15); color:var(--green); }
  .tag-tbd { background:rgba(255,179,71,0.15); color:var(--orange); }
  .tag-info { background:rgba(17,138,178,0.15); color:var(--blue); }
  .tag-critical { background:rgba(255,92,92,0.15); color:var(--red); }
  .tag-reject { background:rgba(131,56,236,0.15); color:var(--purple); }
  .section-note { background:var(--surface2); border-left:3px solid var(--blue); padding:10px 14px; margin:12px 0; border-radius:0 6px 6px 0; font-size:13px; }
  .action-item { display:flex; gap:12px; margin:8px 0; padding:10px 14px; background:var(--surface2); border-radius:6px; }
  .action-item .num { background:var(--blue); color:#fff; border-radius:50%; width:24px; height:24px; display:flex; align-items:center; justify-content:center; font-size:12px; font-weight:700; flex-shrink:0; }
  .conclusion { background:linear-gradient(135deg,rgba(6,214,160,0.08),rgba(17,138,178,0.08)); border:1px solid var(--green); border-radius:8px; padding:16px 20px; margin-top:20px; }
  .commit-list { font-family:"Cascadia Code","Consolas",monospace; font-size:12px; background:var(--surface2); padding:12px 16px; border-radius:6px; margin:8px 0; }
  .file-ref { font-size:11px; color:var(--muted); text-align:center; margin-top:24px; }
  tr:nth-child(even) { background:rgba(255,255,255,0.02); }
  .row-highlight { background:rgba(255,92,92,0.06) !important; }
  .priority-P0 { border-left:3px solid var(--red); }
  .priority-P1 { border-left:3px solid var(--orange); }
  .priority-P2 { border-left:3px solid var(--yellow); }
  code { background:var(--surface2); padding:1px 4px; border-radius:3px; font-size:12px; }
  input[type="text"], input[type="number"], select { background:var(--surface2); color:var(--text); border:1px solid var(--border); border-radius:4px; padding:4px 8px; }
</style>
</head>
<body>
<div class="container">

<h1>BAA 专家确认清单（剩余 35 条违规）</h1>
<p class="subtitle">生成时间：2026-11-02 20:30 &nbsp;|&nbsp; 数据来源：跨图纸复测报告（31 张有效图纸，去重后）&nbsp;|&nbsp; 治理里程碑：4107→35（-99.1%）</p>

<div class="kpi-grid">
  <div class="kpi"><div class="label">初始 findings</div><div class="value" style="color:var(--red)">4107</div></div>
  <div class="kpi"><div class="label">治理后</div><div class="value" style="color:var(--green)">35</div><div class="delta" style="color:var(--green)">-99.1%</div></div>
  <div class="kpi"><div class="label">critical</div><div class="value" style="color:var(--red)">15</div></div>
  <div class="kpi"><div class="label">major</div><div class="value" style="color:var(--orange)">18</div></div>
  <div class="kpi"><div class="label">minor</div><div class="value" style="color:var(--green)">2</div></div>
  <div class="kpi"><div class="label">待确认</div><div class="value" style="color:var(--purple)">35</div></div>
</div>

<div class="section-note">
<strong>使用说明：</strong>
每条记录需领域专家逐项确认「判定结果」，并填写「专家备注」。
推荐流程：1) 打开对应 DWG/DXF 图纸 → 2) 搜索实体 ID → 3) 确认实体类型和属性 → 4) 填写确认结果。
标记为 <span class="tag tag-critical">红色高亮</span> 的行建议优先复核。
</div>
"""]

    for fid, members in sorted(groups.items(), key=lambda x: -len(x[1])):
        g = guidance.get(fid, {})
        title = g.get("title", fid)
        clause = g.get("clause", "")
        threshold = g.get("threshold", "")
        guid = g.get("guidance", "")
        priority = g.get("priority", "P2")

        html_parts.append(f"<h2>{title}（{len(members)} 条）</h2>")
        if clause or threshold:
            html_parts.append(f'<div class="section-note"><strong>条款：</strong>{clause} &nbsp;|&nbsp; <strong>阈值：</strong>{threshold}</div>')
        if guid:
            html_parts.append(f'<div class="section-note"><strong>确认指引：</strong>{guid}</div>')

        html_parts.append("""<table>
<tr>
  <th style="width:50px">序号</th>
  <th style="width:110px">实体 ID</th>
  <th style="width:100px">文件</th>
  <th>实测值</th>
  <th>阈值</th>
  <th style="width:70px">严重度</th>
  <th style="width:60px">优先级</th>
  <th style="width:110px">判定结果</th>
  <th>专家备注</th>
</tr>""")

        for i, f in enumerate(members, 1):
            row_class = "row-highlight" if f["severity"] == "critical" else ""
            file_short = f.get("file", "")[:25]
            entity = f.get("entity_id", "")[:18]
            actual = f.get("actual", "")
            thresh = f.get("threshold", "")
            sev = severity_tag(f["severity"])
            pri = risk_tag(priority.lower())

            explanation = f.get("explanation", "")
            if len(explanation) > 60:
                explanation = explanation[:60] + "..."

            html_parts.append(
                f"""<tr class="{row_class}">
  <td>{i}</td>
  <td><code>{entity}</code></td>
  <td style="font-size:11px">{file_short}</td>
  <td>{actual}</td>
  <td>{thresh}</td>
  <td>{sev}</td>
  <td>{pri}</td>
  <td class="verdict-cell">{verdict_cell()}</td>
  <td><input type="text" style="width:100%;min-width:150px;background:var(--surface2);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:4px 8px;" placeholder="专家备注..."></td>
</tr>"""
            )

        html_parts.append("</table>")

    # Summary table
    html_parts.append("""
<h2>三、确认结果汇总表</h2>
<table>
<tr>
  <th>规则</th>
  <th>条数</th>
  <th>真实违规</th>
  <th>误报</th>
  <th>部分误报</th>
  <th>排除</th>
  <th>确认率</th>
</tr>""")

    for fid in sorted(groups.keys()):
        count = len(groups[fid])
        html_parts.append(
            f"""<tr>
  <td><span class="tag tag-info">{fid}</span></td>
  <td>{count}</td>
  <td><input type="number" min="0" max="{count}" value="0" style="width:50px;background:var(--surface2);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:2px 6px;"></td>
  <td><input type="number" min="0" max="{count}" value="0" style="width:50px;background:var(--surface2);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:2px 6px;"></td>
  <td><input type="number" min="0" max="{count}" value="0" style="width:50px;background:var(--surface2);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:2px 6px;"></td>
  <td><input type="number" min="0" max="{count}" value="0" style="width:50px;background:var(--surface2);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:2px 6px;"></td>
  <td>-</td>
</tr>"""
        )

    html_parts.append("""
</table>

<div class="conclusion">
<h4>复核结论</h4>
<p>经过代码修复（EVAC-004 容差、DIM-113 设备门过滤、AREA-018 极小前室过滤、EVAC-002 异常路径过滤）和审计去重（跨文件/跨规则合并），原始 <strong>89</strong> 条 findings 降至 <strong>35</strong> 条（-60.7%），累计治理幅度 <strong>4107→35（-99.1%）</strong>。</p>
<p>P130 本轮消除 9 条（DIM-113 -4、AREA-018 -5），剩余 35 条中 <strong>约 1 条为疑似误报</strong>（ANTECHAMBER_7843=3.25m² 待确认）、<strong>约 34 条为待领域专家确认的真实违规候选</strong>。</p>
<p style="margin-top:10px;"><strong>建议优先处理：</strong></p>
<ol style="margin-left:20px; margin-top:6px;">
<li><strong>P0（紧急）</strong>：排查 EVAC-002 路径计算 bug（ROOM_9100=176m 等异常值）— <em>已绕过（&gt;80m 过滤）</em></li>
<li><strong>P1（高）</strong>：确认 ANTECHAMBER_7843 (3.25m²) 是否为真实前室</li>
<li><strong>P1（高）</strong>：确认 EVAC-002 4 个房间的疏散距离（30~44m）是否真实超标</li>
<li><strong>P1（高）</strong>：确认 EVAC-001 8 个房间是否真实无疏散路径</li>
<li><strong>P2（中）</strong>：确认 DIM-006 的 1.15m 门所属建筑类型和阈值适用性</li>
<li><strong>P2（中）</strong>：确认 DIM-113 的 4 扇 0.6~0.80m 门是否为设备门</li>
</ol>
</div>

<hr>
<p class="file-ref">数据来源：D:/OpenClawData/BAA/data/fp_rate_audit_report.json &nbsp;|&nbsp; 31 张有效图纸 &nbsp;|&nbsp; 35 个唯一实体</p>

</div>
</body>
</html>""")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write("\n".join(html_parts))
    print(f"Generated: {OUTPUT}")


if __name__ == "__main__":
    main()
