# D3-T2 整改通知单 + 复查意见方案

> **来源**：`docs/roadmap-phase-d-execution-plan.md` 第 3 节 D3-T2  
> **Roadmap 验收**：从审查报告一键生成整改通知单与复查意见  
> **写作日期**：2026-10-27  
> **前置**：T-B6（整改/复查已在 Web 端闭环）、P119（PDF 整改通知单已交付）、D3-T1（模板系统已交付）  
> **本方案范围**：D3-T2（python-docx Word 模板 + SDK 方法 + API 端点），不含 D3-T3/D3-T4

---

## 1. 现状分析

### 1.1 已交付能力
- **PDF 整改通知单**：`src/baa_engine/report_generator/correction_notice.py`（P119 交付），函数 `build_correction_notice(items, review_meta)` 输出 PDF bytes
- **整改闭环**：`src/api/review/review_routes.py` 中已有 `audit.status=confirmed` 标记 + 复查签字字段（T-B6）
- **SDK**：`src/sdk/` 已有 `KnowledgeBundle`，无整改通知单相关方法

### 1.2 缺失能力（D3-T2 增量）
- **Word 模板**：Roadmap 要求 Word 格式（python-docx），方便客户在线编辑/批注
- **复查意见**：整改完成后生成整改项 vs 复查结果对照表（Word）
- **SDK 方法**：`generate_correction_notice(review_id, finding_ids)` + `generate_recheck_opinion(review_id)`
- **API 端点**：`POST /corrections/{review_id}/notice` + `POST /corrections/{review_id}/recheck`

### 1.3 关键文件盘点
| 文件 | 状态 | 说明 |
|------|------|------|
| `src/baa_engine/report_generator/correction_notice.py` | ✅ 已交付 | PDF 版整改通知单（P119） |
| `src/sdk/` | ✅ 已交付 | 无整改相关方法 |
| `python-docx` 依赖 | ❓ 待确认 | 需 `pip install python-docx` |
| `requirements.txt` | ❌ 需追加 | 新增 `python-docx>=1.1.0` |

---

## 2. 改造目标与验收标准

### 2.1 Roadmap DoD（原文）
- [ ] `src/baa_engine/report_generator/correction_notice.py`：输入 review_id + 需整改 finding 列表 → 输出 Word 模板（python-docx）
- [ ] 模板字段：项目信息 / 整改内容 / 整改要求 / 整改期限 / 整改人 / 发单日期
- [ ] 复查意见：整改完成后生成 Word（整改项 vs 复查结果对照表）
- [ ] SDK 新增 `generate_correction_notice(review_id, finding_ids)` 方法

### 2.2 本方案验收标准
| 验收项 | 标准 |
|--------|------|
| Word 整改通知单 | `python-docx` 生成 .docx，包含封面 + 整改清单 + 签字页 |
| Word 复查意见 | 整改项 vs 复查结果对照表，复查状态（通过/不通过/待补） |
| 模板字段完整 | 项目名/甲方/乙方/发单日期/整改期限/整改人/复查人/签字栏 |
| SDK 方法 | `sdk.generate_correction_notice(review_id, finding_ids)` 输出 .docx 路径 |
| API 端点 | `POST /corrections/{review_id}/notice` + `POST /corrections/{review_id}/recheck` |
| 回归 | 全量后端测试 0 退化 |

---

## 3. 改造范围（分阶段）

### 3.1 阶段 A：python-docx Word 生成服务（1 天）

**目标**：新建 Word 整改通知单 + 复查意见生成模块。

**改动**：
1. 新建 `src/baa_engine/word_generator/__init__.py`
2. 新建 `src/baa_engine/word_generator/correction_docx.py`：
   - `build_correction_notice_docx(items, review_meta, output_path) -> str`
   - `build_recheck_opinion_docx(rechecks, review_meta, output_path) -> str`
3. 追加 `requirements.txt`：`python-docx>=1.1.0`

**Word 整改通知单结构**：
```
┌─ 封面页 ─────────────────────┐
│  整改通知单 (大标题)          │
│  CORRECTION NOTICE           │
│  编号 / 项目 / 图纸 / 审查人  │
│  日期                        │
│  统计卡片 (违规/条款/图元)    │
└───────────────────────────────┘
┌─ 整改清单页 ─────────────────┐
│  按 function_id 分组          │
│  序号 | 图元 | 批注 | 整改要求 │
│  复查栏 + 签字栏              │
└───────────────────────────────┘
┌─ 签字页 ─────────────────────┐
│  项目负责人确认 + 签字栏      │
└───────────────────────────────┘
```

**Word 复查意见结构**：
```
┌─ 封面页 ─────────────────────┐
│  复查意见 (大标题)            │
│  RECHECK OPINION              │
│  编号 / 项目 / 图纸 / 复查人  │
│  日期                        │
└───────────────────────────────┘
┌─ 对照表页 ───────────────────┐
│  整改项 | 复查状态 | 复查意见 │
│  101-01 | 通过     | 已符合   │
│  101-02 | 不通过   | 厚度仍不足│
│  ...                          │
└───────────────────────────────┘
┌─ 签字页 ─────────────────────┐
│  复查人 / 整改人 双签字栏     │
└───────────────────────────────┘
```

### 3.2 阶段 B：API 端点 + SDK 方法（0.5 天）

**改动**：
1. 新建 `src/api/corrections/__init__.py` + `correction_routes.py`：
   - `POST /api/v1/corrections/{review_id}/notice` → Word 文件流下载
   - `POST /api/v1/corrections/{review_id}/recheck` → Word 文件流下载
2. 注册到 `baa_api.py`
3. SDK 新增 `src/sdk/baa_sdk/corrections.py`：
   - `generate_correction_notice(review_id, finding_ids=None) -> str`（返回本地 .docx 路径）
   - `generate_recheck_opinion(review_id) -> str`

### 3.3 阶段 C：验收测试（0.5 天）

**改动**：
- `src/tests/test_correction_docx.py`（5 用例）：
  1. Word 整改通知单生成 → 文件存在且可被 python-docx 读取
  2. Word 复查意见生成 → 文件存在且含对照表
  3. SDK generate_correction_notice 输出路径正确
  4. POST /corrections/{rid}/notice 端点返回 200 + Content-Type=application/vnd.openxmlformats-officedocument.wordprocessingml.document
  5. 未知 review_id → 404
- 全量后端回归（2659+ 用例）

**验收**：手动打开生成的 .docx，表格/字体/分页正常。

---

## 4. 关键设计决策

### 4.1 与现有 PDF 整改通知单的关系
- PDF 版（P119）保留，不删除
- Word 版（D3-T2）作为**优先格式**（Roadmap 明确要求）
- 两套格式并存：API/SDK 默认返回 Word，可通过 `format=pdf` 参数切换

### 4.2 python-docx vs reportlab Word
- 选 python-docx：Roadmap 明确要求；python-docx 生成 .docx 原生 Word 格式，支持客户在线编辑；reportlab 不支持 .docx 输出
- 注意：python-docx 不支持中文字体自动嵌入，需系统安装宋体/微软雅黑；Word 打开时会自动回退

### 4.3 模板字段映射
| Word 字段 | 数据源 |
|-----------|--------|
| 项目名 | `review_meta.project_name` |
| 甲方 | `review_meta.client`（可选，缺省"—"） |
| 乙方 | 固定"BAA 智能审查平台" |
| 审查人 | `review_meta.reviewer` |
| 整改人 | `review_meta.corrector`（可选） |
| 复查人 | `review_meta.reviewer`（缺省同审查人） |
| 发单日期 | `datetime.now()` |
| 整改期限 | `review_meta.deadline`（可选，缺省"—"） |
| 图纸名称 | `review_meta.drawing_name` |
| 审查编号 | `review_id` |

### 4.4 SDK 方法签名
```python
# src/sdk/baa_sdk/corrections.py
def generate_correction_notice(
    review_id: str,
    finding_ids: list[str] | None = None,
    output_dir: str | None = None,
    format: Literal["docx", "pdf"] = "docx",
) -> str:
    """生成整改通知单，返回输出文件路径。"""

def generate_recheck_opinion(
    review_id: str,
    output_dir: str | None = None,
    format: Literal["docx", "pdf"] = "docx",
) -> str:
    """生成复查意见，返回输出文件路径。"""
```

---

## 5. 风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| python-docx 中文字体缺失 | Word 打开后显示方框 | 安装宋体/微软雅黑；docx 内嵌字体提示 |
| 现有 PDF 整改通知单调用方 | 可能被误改 | PDF 版保留不动，Word 版新增独立模块 |
| 大表格分页溢出 | Word 表格跨页格式错乱 | python-docx 原生支持跨页表格，设 `allow_autofit=True` |

---

## 6. 执行 Checklist

### 6.1 阶段 A：Word 生成（1 天）
- [ ] `pip install python-docx>=1.1.0` + requirements.txt 追加
- [ ] `src/baa_engine/word_generator/__init__.py`
- [ ] `src/baa_engine/word_generator/correction_docx.py`（整改通知单 + 复查意见）
- [ ] Word 字体/表格样式定义

### 6.2 阶段 B：API + SDK（0.5 天）
- [ ] `src/api/corrections/correction_routes.py`（2 端点）
- [ ] `baa_api.py` 注册 router
- [ ] `src/sdk/baa_sdk/corrections.py`（2 方法）

### 6.3 阶段 C：测试 + commit（0.5 天）
- [ ] `test_correction_docx.py`（5 用例）
- [ ] 全量回归
- [ ] 手动验收 .docx
- [ ] commit

**总计**：2 天

---

## 7. 依赖与前置
- **T-B6 整改闭环**：已交付（audit.status=confirmed + 复查字段）
- **P119 PDF 整改通知单**：已交付（可复用元数据结构）
- **D3-T1 模板系统**：已交付（Word 模板可复用配色字段）

---

## 8. 后续任务
- **D3-T3 客户成功 SOP**：落地文档 + review_projects 表 + API
- **D3-T4 交付物版本化**：manifest schema_version + SDK 兼容矩阵
- **D4-T1~T4 SLA 与付费闭环**

---

## 9. 附录

### 9.1 关键文件路径（新建/修改）
| 操作 | 路径 |
|------|------|
| 新建 | `src/baa_engine/word_generator/__init__.py` |
| 新建 | `src/baa_engine/word_generator/correction_docx.py` |
| 新建 | `src/api/corrections/__init__.py` |
| 新建 | `src/api/corrections/correction_routes.py` |
| 修改 | `src/baa_api.py`（注册 router） |
| 新建 | `src/sdk/baa_sdk/corrections.py` |
| 修改 | `requirements.txt`（追加 python-docx） |
| 新建 | `src/tests/test_correction_docx.py` |

### 9.2 python-docx 最小可用示例（设计参考）
```python
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

doc = Document()
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run("整改通知单")
run.font.size = Pt(28)
run.font.color.rgb = RGBColor(0x1a, 0x36, 0x5d)

table = doc.add_table(rows=1, cols=4)
table.style = "Light Grid Accent 1"
hdr = table.rows[0].cells
hdr[0].text = "序号"
...
```

### 9.3 Word vs PDF 对比
| 维度 | python-docx (.docx) | reportlab (.pdf) |
|------|---------------------|-------------------|
| 客户可编辑 | ✅ 原生 Word | ❌ |
| 打印保真 | ✅ Word 自己 | ✅ 完美 |
| 中文字体 | 需系统安装 | 内嵌 WQY 字体 |
| 表格跨页 | ✅ 原生支持 | 需手动 PageBreak |
| Roadmap 要求 | ✅ 明确要求 Word | — |
