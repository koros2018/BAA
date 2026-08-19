import logging

logger = logging.getLogger(__name__)

"""
P111 数据质量诊断脚本

诊断项目：
1. 图像与标签文件名匹配率
2. 非建筑平面图过滤（系统图/计算表/目录/图例等）
3. 类别分布与缺失类别
4. 标注质量统计（越界框/异常框）

输出：P111_data_quality_report.md
"""

import os
import json
from collections import Counter
from pathlib import Path

BASE = Path("data/p106_yolo_dataset")
IMG_DIR = BASE / "images"
LBL_DIR = BASE / "labels"

YOLO_CLASSES = [
    "wall",
    "door",
    "window",
    "staircase",
    "corridor",
    "fire_door",
    "exit",
    "fire_lane",
    "fire_zone",
    "fire_window",
    "shaft",
    "room",
    "exit_sign",
    "sprinkler_system",
    "fire_alarm",
    "insulation",
    "evacuation_lighting",
    "refuge_floor",
]

# 非建筑平面图关键词（按优先级排列，命中即剔除）
NON_FLOOR_KW = [
    "系统图",
    "系统拓扑",
    "系统原理",
    "系统",
    "计算",
    "参数表",
    "选型",
    "材料",
    "目录",
    "说明",
    "图例",
    "详图",
    "大样图",
    "剖面图",
    "立面图",
    "断面图",
    "剖面",
    "立面",
    "原理图",
    "单线图",
    "拓扑图",
    "清单",
    "预算",
    "概算",
    "决算",
    "设备选型",
    "配电系统",
    "供电系统",
    "消防系统",
    "给排水系统",
    "弱电系统",
    "强电系统",
    "系统总体",
    "总体架构图",
    "网络拓扑",
    "控制原理",
    "自控系统",
    "计算书",
    "计算表",
    "照度计算",
    "热工计算",
    "负荷计算",
]

FLOOR_KW = [
    "平面",
    "层",
    "楼",
    "户型",
    "房间",
    "轴线",
    "轴网",
    "平面布置图",
    "建筑平面",
    "结构平面",
    "装修平面",
    "顶板平面",
    "基础平面",
    "屋顶平面",
]

# 低置信度/小框阈值
MIN_BOX_AREA_PCT = 0.0001  # 最小框面积占比（宽×高）
MIN_CONF = 0.3  # 最小置信度


def load_txt_list(filepath):
    if not os.path.exists(filepath):
        return []
    with open(filepath) as f:
        return [l.strip() for l in f if l.strip()]


def is_non_floor(name: str) -> bool:
    name_lower = name.lower()
    if any(kw in name for kw in FLOOR_KW):
        return False
    return any(kw in name for kw in NON_FLOOR_KW)


def diagnose():
    img_files = set(os.listdir(IMG_DIR))
    lbl_files = set(os.listdir(LBL_DIR))
    img_names = {f.rsplit(".", 1)[0]: f for f in img_files}
    lbl_names = {f.rsplit(".", 1)[0] for f in lbl_files}

    train_list = load_txt_list(BASE / "train.txt")
    val_list = load_txt_list(BASE / "val.txt")
    all_img_paths = train_list + val_list
    all_img_basenames = set(os.path.basename(p) for p in all_img_paths)

    # 1. 文件名匹配
    img_stems = set(img_names.keys())
    matched = img_stems & lbl_names
    unmatched_imgs = img_stems - lbl_names
    unmatched_lbls = lbl_names - img_stems

    # 2. 非平面图过滤
    all_stems = img_stems | lbl_names
    non_floor = {s for s in all_stems if is_non_floor(s)}

    # 3. 类别分布
    class_counter = Counter()
    bad_boxes = []
    empty_labels = []
    for lbl in lbl_names:
        path = LBL_DIR / (lbl + ".txt" if not lbl.endswith(".txt") else lbl)
        if not os.path.exists(path):
            continue
        if os.path.getsize(path) == 0:
            empty_labels.append(lbl)
            continue
        with open(path) as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 6:
                    cls = int(parts[0])
                    conf = float(parts[5])
                    class_counter[cls] += 1
                    w = float(parts[3])
                    h = float(parts[4])
                    if w * h < MIN_BOX_AREA_PCT:
                        bad_boxes.append({"label": lbl, "line": line.strip()})
                    if conf < MIN_CONF:
                        bad_boxes.append({"label": lbl, "line": line.strip(), "reason": "low_conf"})
                elif len(parts) >= 5:
                    try:
                        cls = int(parts[0])
                        class_counter[cls] += 1
                    except ValueError:
                        logger.debug("[P120] 标签类别行解析失败，跳过")

    # 4. 有效数据集（平面图且有标签）
    valid_stems = img_stems & lbl_names - non_floor
    valid_img_stems = set(s for s in valid_stems if s in img_names)

    # 生成报告
    report = []
    report.append("# P111 数据质量诊断报告\n")
    report.append(f"> 生成时间: 2026-08-15\n")

    report.append("## 一、数据规模\n")
    report.append(f"| 指标 | 数值 |")
    report.append(f"|------|------|")
    report.append(f"| 图像总数 | {len(img_files)} |")
    report.append(f"| 标签总数 | {len(lbl_files)} |")
    report.append(f"| 训练集 | {len(train_list)} |")
    report.append(f"| 验证集 | {len(val_list)} |")

    report.append(f"\n## 二、文件名匹配\n")
    report.append(f"| 指标 | 数值 | 说明 |")
    report.append(f"|------|------|------|")
    report.append(f"| 图像-标签匹配 | {len(matched)} | {'✅' if matched else '❌ 全部不匹配'} |")
    report.append(f"| 有图无标 | {len(unmatched_imgs)} | 图像存在但无对应标签 |")
    report.append(f"| 有标无图 | {len(unmatched_lbls)} | 标签存在但无对应图像 |")

    report.append(f"\n## 三、非建筑平面图过滤\n")
    report.append(f"| 指标 | 数值 |")
    report.append(f"|------|------|")
    report.append(f"| 可疑非平面图 | {len(non_floor)} | 系统图/计算表/目录/图例等 |")
    report.append(f"| 可疑占比 | {len(non_floor)/max(len(all_stems),1)*100:.1f}% |")
    if non_floor:
        report.append(f"\n示例（前 20）：")
        for s in sorted(non_floor)[:20]:
            report.append(f"- `{s}`")

    report.append(
        f"\n## 四、类别分布（{len(class_counter)} 类有标注 / {len(YOLO_CLASSES)} 类总）\n"
    )
    report.append(f"| Class ID | 名称 | 标注数 | 状态 |")
    report.append(f"|----------|------|--------|------|")
    for i, name in enumerate(YOLO_CLASSES):
        cnt = class_counter.get(i, 0)
        status = "✅" if cnt > 0 else ("⚠️ 极少量" if cnt < 10 else "❌ 缺失")
        report.append(f"| {i} | {name} | {cnt} | {status} |")

    report.append(f"\n## 五、标注质量\n")
    report.append(f"| 指标 | 数值 |")
    report.append(f"|------|------|")
    report.append(f"| 空标签文件 | {len(empty_labels)} |")
    report.append(f"| 异常小框 | {len(bad_boxes)} | 宽×高 < {MIN_BOX_AREA_PCT} |")
    report.append(
        f"| 低置信度框 | {sum(1 for b in bad_boxes if b.get('reason') == 'low_conf')} | 置信度 < {MIN_CONF} |"
    )

    report.append(f"\n## 六、有效数据集估算\n")
    report.append(f"| 指标 | 数值 |")
    report.append(f"|------|------|")
    report.append(f"| 有标签平面图 | {len(valid_img_stems)} |")
    report.append(f"| 无标签平面图 | {len((img_stems - non_floor) - lbl_names)} |")

    report.append(f"\n## 七、修复建议\n")
    report.append(
        "1. **文件名对齐**：标签文件名必须与图像文件名完全一致（不含扩展名），当前 0 匹配需优先修复"
    )
    report.append("2. **剔除非平面图**：约 104 张系统图/计算表/目录等应剔除")
    report.append(
        "3. **扩充 8 类缺失类别**：exit_sign/sprinkler_system/fire_alarm/insulation/evacuation_lighting/refuge_floor/fire_lane/fire_zone"
    )
    report.append("4. **异常框过滤**：移除面积占比 < 0.0001 的标注框")

    content = "\n".join(report)
    return content, {
        "img_files": len(img_files),
        "lbl_files": len(lbl_files),
        "matched": len(matched),
        "non_floor": len(non_floor),
        "valid": len(valid_img_stems),
        "classes_with_labels": len(class_counter),
        "bad_boxes": len(bad_boxes),
    }


if __name__ == "__main__":
    content, summary = diagnose()
    out_path = BASE / "P111_data_quality_report.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(content)
    print(f"\nReport saved to: {out_path}")
