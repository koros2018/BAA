#!/usr/bin/env python3
"""
P96: 施工图审查 SFT 数据集生成脚本

输出目录: /tmp/p96_sft/
  - all.jsonl         — 完整数据集（静态规则 + 审查样本）
  - atomic_functions.jsonl  — 422 条原子函数
  - layer_rules.jsonl — 838 条图层语义映射
  - construction_review.jsonl — 30 条施工图审查标准
  - review_samples.jsonl  — 审查历史样本（有数据时）
  - hf_dataset_description.json — HuggingFace Dataset 描述
  - dataset_manifest.json — 数据集清单
"""

import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.baa_engine.atomic_functions import FuncRegistry
from src.baa_engine.model_params.exporter import (
    get_function_params,
    get_layer_rules,
    get_construction_review_params,
    get_review_samples,
    to_sft_jsonl,
    to_hf_dataset_description,
)

OUTPUT_DIR = os.environ.get("P96_OUTPUT_DIR", "/tmp/p96_sft")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def generate_static_dataset() -> list[dict]:
    """生成静态规则 SFT 数据集（原子函数 + 图层规则 + CD 审查项）"""
    registry = FuncRegistry()
    funcs = get_function_params(registry)
    rules = get_layer_rules()
    cd_items = get_construction_review_params()

    jsonl_text = to_sft_jsonl(funcs, rules, cd_items)
    lines = [json.loads(line) for line in jsonl_text.strip().split("\n")]

    # 写入分文件
    by_source: dict[str, list[str]] = {}
    for data in lines:
        src = data.get("metadata", {}).get("source", "unknown")
        by_source.setdefault(src, []).append(json.dumps(data, ensure_ascii=False))

    for src, records in by_source.items():
        path = os.path.join(OUTPUT_DIR, f"{src}.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(records) + "\n")
        print(f"  {src}: {len(records)} 条 → {path}")

    # 写入完整合并文件
    all_path = os.path.join(OUTPUT_DIR, "all.jsonl")
    with open(all_path, "w", encoding="utf-8") as f:
        f.write(jsonl_text + "\n")
    print(f"  完整数据集: {len(lines)} 条 → {all_path}")

    # HF dataset description
    hf_desc = to_hf_dataset_description(funcs, rules, cd_items)
    hf_path = os.path.join(OUTPUT_DIR, "hf_dataset_description.json")
    with open(hf_path, "w", encoding="utf-8") as f:
        json.dump(hf_desc, f, ensure_ascii=False, indent=2)
    print(f"  HF 描述: → {hf_path}")

    return lines


def generate_review_dataset() -> list[dict]:
    """生成审查历史 SFT 数据集（动态样本）"""
    raw_samples = get_review_samples(limit=20)
    if not raw_samples:
        print("  审查历史为空，跳过动态样本")
        return []

    review_lines = []
    for sample in raw_samples:
        task_id = sample.get("task_id", "")
        features = sample.get("input_features", {})
        decisions = sample.get("decisions", [])

        # 每个 decision 是一条样本
        for dec in decisions:
            input_text = (
                f"图纸: {features.get('drawing_name', '')}\n"
                f"审查任务: {task_id}\n"
                f"实体ID: {dec.get('input_features', {}).get('entity_id', '')}\n"
                f"实体类型: {dec.get('input_features', {}).get('entity_type', '')}\n"
                f"原子函数: {dec.get('input_features', {}).get('func_id', '')}\n"
                f"条款: {dec.get('input_features', {}).get('clause_id', '')}\n"
                f"实际值: {dec.get('input_features', {}).get('extracted_value', '')}\n"
                f"要求值: {dec.get('input_features', {}).get('required_value', '')}\n"
                f"偏差: {dec.get('input_features', {}).get('difference', '')}\n"
                f"置信度: {dec.get('input_features', {}).get('confidence', '')}"
            )
            output_text = (
                f"判定: {dec.get('output_label', 'FAIL')}\n"
                f"依据: {dec.get('rationale', '')}\n"
                f"规范: {dec.get('standard_ref', '')}"
            )
            if dec.get("suggestion"):
                output_text += f"\n建议: {dec.get('suggestion', '')}"

            review_lines.append({
                "messages": [
                    {"role": "user", "content": f"判断以下施工图审查结果是否合理：\n{input_text}"},
                    {"role": "assistant", "content": output_text},
                ],
                "metadata": {
                    "source": "review_samples",
                    "task_id": task_id,
                    "output_label": dec.get("output_label", "FAIL"),
                    "drawing_name": features.get("drawing_name", ""),
                },
            })

    if review_lines:
        path = os.path.join(OUTPUT_DIR, "review_samples.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for line in review_lines:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
        print(f"  review_samples: {len(review_lines)} 条 → {path}")

    return review_lines


def build_manifest(static_lines: list[dict], review_lines: list[dict]) -> dict:
    """构建数据集清单"""
    all_lines = static_lines + review_lines

    sources = Counter(d["metadata"]["source"] for d in all_lines)
    categories = Counter()
    for d in all_lines:
        meta = d["metadata"]
        cat = meta.get("category", meta.get("major", meta.get("entity_type", "unknown")))
        categories[cat] += 1

    manifest = {
        "dataset_name": "BAA_construction_review_sft",
        "description": "BAA 施工图审查 SFT 数据集，包含静态规则（原子函数/图层规则/审查标准）和动态审查样本",
        "version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_samples": len(all_lines),
        "by_source": dict(sources.most_common()),
        "by_category": dict(categories.most_common(20)),
        "files": [
            "all.jsonl",
            "atomic_functions.jsonl",
            "layer_rules.jsonl",
            "construction_review.jsonl",
            "review_samples.jsonl",
            "hf_dataset_description.json",
        ],
        "usage": {
            "hf_datasets": "datasets.load_dataset('json', data_files='all.jsonl')",
            "openai_finetune": "训练数据需转为 messages 字段格式，每条一个 JSONL 行",
            "qwen_deepseek": "直接使用 jsonl-sft 格式，字段结构与 OpenAI 兼容",
        },
    }

    path = os.path.join(OUTPUT_DIR, "dataset_manifest.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"  数据集清单: → {path}")
    return manifest


def main():
    print("=== P96: SFT 数据集生成 ===")
    print(f"输出目录: {OUTPUT_DIR}\n")

    print("1. 静态规则数据集:")
    static_lines = generate_static_dataset()
    print()

    print("2. 审查历史数据集:")
    review_lines = generate_review_dataset()
    print()

    print("3. 数据集清单:")
    manifest = build_manifest(static_lines, review_lines)
    print()

    print(f"=== 完成 ===")
    print(f"总样本数: {manifest['total_samples']}")
    print(f"数据源: {manifest['by_source']}")


if __name__ == "__main__":
    main()