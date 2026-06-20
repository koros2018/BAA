# DD-5：规范JSON库构建方案——详细设计文档

> **所属阶段：** 工程设计（详细设计）
> **对应架构层：** 核心推理层 → 知识库
> **编制日期：** 2026-06-09
> **批准依据：** Master批准（决策DD-08: 20条, DD-09: LLM初稿+master审核）
> **前提约束：** 零成本创业模式，LLM用Qwen2-1.5B本地部署

---

## 1. 设计概述

### 1.1 设计目标

构建BAA规范判定知识库，首批10条L1级规范，格式一次性定好。

**核心指标（终稿定稿，2026-06-20）：**
- 首批数量：**10条**（全部L1级，GB50016建筑防火规范）
- 框架预留：支持扩展至100条+，格式不变
- 规范JSON格式：一次性定好，后续扩展不重构
- 覆盖范围：GB50016建筑防火规范

### 1.2 参考来源

| 参考来源 | 贡献 | 复用程度 |
|---------|------|---------|
| 论文#8 (Fine-Tuning LLM, 53%→82.7%) | 规范QA准确率基准 | 🟢 目标参考 |
| 论文#9 (Table Comprehension, 41%→86%) | 规范表格提取方法 | 🟢 约束条件 |
| 论文#1 (LLM-FuncMapper) | 条款→原子函数映射 | 🟢 方法参考 |
| 论文#11 (RADIANT-LLM) | human-in-the-loop审核回路 | 🟢 完全复用 |
| 参考1论文数据集分层 | 主/验/辅/反馈四层策略 | 🟢 完全复用 |
| 可研报告v3.0 | 技术架构指标要求 | 🟢 约束条件 |

---

## 2. 构建流程

### 2.1 四步构建流程

```
Step 1: 规范文本解析
  └─ 用Qwen2-1.5B从GB50016原文提取：
     ├─ 条款编号 + 条款正文
     ├─ 表格数据（如疏散距离表）
     └─ 条件逻辑（如"当建筑高度>100m时"）
  └─ 参考论文#9：VLM微调后表格提取86%
  └─ 输出: 规范JSON初稿（AI生成）

Step 2: 原子函数映射
  └─ 用LLM将每个条款匹配到原子函数
     ├─ 条款5.5.18 "疏散楼梯净宽≥1.2m" → AF-DIM-001
     └─ 条款6.1.1 "防火分区面积≤2500㎡" → AF-DIM-002
  └─ 参考论文#1：LLM-FuncMapper比纯微调高19%
  └─ 输出: 原子函数匹配表

Step 3: 人工审核 (human-in-the-loop)
  └─ master逐条审核规范JSON的正确性
     ├─ 条款编号正确
     ├─ 阈值/单位正确
     ├─ 条件逻辑正确
     └─ 原子函数映射正确
  └─ 发现错误→修正→加入反馈数据集
  └─ 参考论文#11：RADIANT-LLM审核回路
  └─ 输出: 已确认的规范JSON

Step 4: 质量评估
  └─ 用测试集评估规范JSON准确率
  └─ 目标：L1级≥85%判定准确率
  └─ 参考论文#8：微调后82.7%
  └─ 输出: 质量评估报告
```

### 2.2 工具链

| 步骤 | 工具 | 角色 | 成本 |
|------|------|------|------|
| Step 1 文本解析 | Qwen2-1.5B (Ollama) | 生成JSON初稿 | ¥0 |
| Step 2 函数映射 | Qwen2-1.5B (Ollama) | 推荐原子函数 | ¥0 |
| Step 3 人工审核 | Master | 确认/修正 | — |
| Step 4 质量评估 | 单元测试脚本 | 自动验证 | ¥0 |

---

## 3. 规范JSON格式

### 3.1 JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["clause_id", "standard", "title", "text", "level", 
               "category", "atomic_func", "parameters"],
  "properties": {
    "clause_id": {
      "type": "string",
      "description": "条款编号",
      "example": "GB50016-5.5.18"
    },
    "standard": {
      "type": "string",
      "description": "国家标准编号",
      "example": "GB 50016-2014"
    },
    "standard_name": {
      "type": "string",
      "description": "国家标准名称",
      "example": "建筑设计防火规范"
    },
    "title": {
      "type": "string",
      "description": "条款标题",
      "example": "疏散楼梯净宽"
    },
    "text": {
      "type": "string",
      "description": "规范原文",
      "example": "高层公共建筑的疏散楼梯，其净宽度不应小于1.2m。"
    },
    "level": {
      "type": "string",
      "enum": ["L1", "L2", "L3"],
      "description": "规范级别：L1=强制+常见, L2=强制+低频, L3=推荐"
    },
    "category": {
      "type": "string",
      "enum": ["fire_safety", "structural", "accessibility", 
               "waterproof", "hvac", "plumbing", "electrical", 
               "lighting", "drawing_standard"],
      "description": "规范类别"
    },
    "atomic_func": {
      "type": "string",
      "description": "对应的原子函数ID",
      "example": "AF-DIM-001"
    },
    "parameters": {
      "type": "object",
      "description": "判定参数",
      "properties": {
        "entity_type": {
          "type": "string",
          "description": "目标图元类型"
        },
        "property": {
          "type": "string",
          "description": "判定属性"
        },
        "operator": {
          "type": "string",
          "enum": [">=", "<=", ">", "<", "==", "!=", "exists"],
          "description": "判定操作符"
        },
        "threshold": {
          "type": ["number", "string", "array"],
          "description": "阈值（数值/枚举值/条件列表）"
        },
        "unit": {
          "type": "string",
          "description": "单位",
          "example": "m"
        },
        "conditions": {
          "type": "array",
          "description": "前置条件（如建筑类型/高度要求）",
          "items": {
            "type": "object",
            "properties": {
              "param": {"type": "string"},
              "operator": {"type": "string"},
              "value": {"type": ["string", "number"]}
            }
          }
        }
      },
      "required": ["entity_type", "property", "operator", "threshold"]
    },
    "severity": {
      "type": "string",
      "enum": ["critical", "major", "minor", "info"],
      "description": "违规严重等级"
    },
    "suggestion_template": {
      "type": "string",
      "description": "修改建议模板（可填充参数）",
      "example": "建议将{entity_id}的{property}增加至≥{threshold}{unit}"
    },
    "exceptions": {
      "type": "array",
      "description": "例外情况",
      "items": {
        "type": "object",
        "properties": {
          "condition": {"type": "string"},
          "alternative": {"type": "string"}
        }
      }
    },
    "source": {
      "type": "string",
      "enum": ["manual", "llm_generated", "llm_reviewed"],
      "description": "规范来源"
    },
    "status": {
      "type": "string",
      "enum": ["draft", "reviewed", "verified", "active"],
      "description": "规范状态"
    },
    "changelog": {
      "type": "array",
      "description": "变更记录",
      "items": {
        "type": "object",
        "properties": {
          "date": {"type": "string"},
          "version": {"type": "string"},
          "change": {"type": "string"},
          "author": {"type": "string"}
        }
      }
    }
  }
}
```

### 3.2 规范JSON示例

```json
{
  "clause_id": "GB50016-5.5.18",
  "standard": "GB 50016-2014",
  "standard_name": "建筑设计防火规范",
  "title": "疏散楼梯净宽",
  "text": "高层公共建筑的疏散楼梯，其净宽度不应小于1.2m。",
  "level": "L1",
  "category": "fire_safety",
  "atomic_func": "AF-DIM-001",
  "parameters": {
    "entity_type": "staircase",
    "property": "clear_width",
    "operator": ">=",
    "threshold": 1.2,
    "unit": "m",
    "conditions": [
      {"param": "building_type", "operator": "==", "value": "高层公共建筑"}
    ]
  },
  "severity": "major",
  "suggestion_template": "建议将{entity_id}的梯段宽度增加至≥{threshold}{unit}，或调整楼梯间布局。",
  "exceptions": [],
  "source": "llm_generated",
  "status": "active",
  "changelog": [
    {"date": "2026-06-09", "version": "1.0", "change": "初始版本", "author": "LLM初稿+master审核"}
  ]
}
```

---

## 4. 首批20条规范清单

### 4.1 L1级（10条，强制+常见）

| # | 条款编号 | 规范内容 | 原子函数 | 优先级 |
|---|---------|---------|---------|:-----:|
| 1 | GB50016-5.5.18 | 疏散楼梯净宽≥1.2m | AF-DIM-001 | P0 |
| 2 | GB50016-5.5.17 | 疏散距离≤30m | AF-DIST-001 | P0 |
| 3 | GB50016-6.1.1 | 防火分区面积≤2500㎡ | AF-DIM-002 | P0 |
| 4 | GB50016-5.5.8 | 安全出口≥2个 | AF-COUNT-001 | P0 |
| 5 | GB50016-6.5.1 | 防火门等级要求（甲级） | AF-ATTR-001 | P1 |
| 6 | GB50016-7.1.1 | 消防车道宽度≥4m | AF-DIM-003 | P1 |
| 7 | GB50016-7.2.2 | 消防登高面要求（存在性） | AF-EXIST-002 | P1 |
| 8 | GB50016-5.5.12 | 疏散楼梯间设置要求 | AF-EXIST-001 | P1 |
| 9 | GB50016-6.2.9 | 防火墙/防火隔墙设置 | AF-REL-001 | P2 |
| 10 | GB50016-8.3.3 | 自动喷水灭火系统设置 | AF-EXIST-003 | P2 |

### 4.2 L2级（10条，强制+低频）

| # | 条款编号 | 规范内容 | 原子函数 | 优先级 |
|---|---------|---------|---------|:-----:|
| 11 | GB50016-5.5.21 | 观众厅疏散宽度 | AF-DIM-004 | P2 |
| 12 | GB50016-6.1.5 | 防火墙上开设门窗 | AF-REL-002 | P2 |
| 13 | GB50016-7.3.1 | 消防电梯设置范围 | AF-EXIST-004 | P2 |
| 14 | GB50016-7.3.5 | 消防电梯载重量 | AF-ATTR-002 | P2 |
| 15 | GB50016-8.2.1 | 室内消火栓设置 | AF-EXIST-005 | P2 |
| 16 | GB50016-8.4.1 | 火灾自动报警系统 | AF-EXIST-006 | P2 |
| 17 | GB50016-9.1.3 | 防烟设施设置 | AF-EXIST-007 | P3 |
| 18 | GB50016-9.2.2 | 自然排烟窗面积 | AF-DIM-005 | P3 |
| 19 | GB50016-10.1.5 | 消防电源切换时间 | AF-ATTR-003 | P3 |
| 20 | GB50016-10.3.1 | 疏散照明照度 | AF-DIM-006 | P3 |

---

## 5. 数据分层策略（迁移自参考1论文数据集体系）

| 数据层级 | 参考1论文 | BAA对应 | 规模 | 用途 |
|---------|---------|--------|:----:|------|
| **主规范库** | FER-2013 (35,887张) | GB50016规范JSON | 20条 | 规范判定依据 |
| **验证集** | CK+ (精确标注) | 3-5张真实图纸 | 3-5张 | 验证规范JSON正确性 |
| **辅助集** | JAFFE (文化差异) | 地方标准差异 | 视需求 | 深圳/上海等差异测试 |
| **反馈集** | AffectNet (40万张) | 用户反馈数据 | 持续积累 | 数据飞轮 |

---

## 6. 交付物清单

| 交付物 | 格式 | 说明 |
|--------|------|------|
| `specs_v1.0.json` | JSON | 首批20条规范JSON |
| `spec_schema.json` | JSON Schema | 规范JSON格式定义 |
| `spec_repository.py` | Python | 规范库读写+检索接口 |
| `llm_spec_helper.py` | Python | LLM辅助生成规范JSON初稿 |
| `spec_validator.py` | Python | 规范JSON格式校验器 |

---

*编制：司军（AI业务助理）*
*日期：2026-06-09*
*决策依据：DD-08(20条) + DD-09(LLM初稿+master审核)*