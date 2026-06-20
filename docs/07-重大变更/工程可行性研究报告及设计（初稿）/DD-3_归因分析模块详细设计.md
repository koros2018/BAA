# DD-3：归因分析模块——详细设计文档

> **所属阶段：** 工程设计（详细设计）
> **对应架构层：** 核心推理层 → 输出展示层
> **编制日期：** 2026-06-09
> **批准依据：** Master批准（决策DD-06: 三要素+轻量级注意力热力图）
> **前提约束：** 零成本创业模式，热力图用规则标注而非模型训练

---

## 1. 设计概述

### 1.1 设计目标

为BAA每个违规判定提供完整可追溯的归因分析，增强用户对AI审查结果的信任。

**核心指标：**
- 归因三要素完备率：**100%**（每个判定含规范依据+参数证据+判定逻辑）
- 注意力热力图覆盖率：**≥90%**（每个判定含关注图元及权重）
- 合规要求：满足论文#16（Explainability as Compliance Requirement）

### 1.2 参考来源

| 参考来源 | 贡献 | 复用程度 |
|---------|------|---------|
| 论文#3 (LLM Attribution for Code Compliance) | 归因分析方法论 | 🟢 完全复用 |
| 论文#16 (Explainability as Compliance) | 合规要求可解释性 | 🟢 约束条件 |
| 参考1论文4.3.3 (注意力机制) | 注意力热力图概念迁移 | 🟡 规则化适配 |
| DD-1 原子函数库 | 判定结果输入 | 🟢 接口对接 |
| DD-6 前端UI | 热力图展示组件 | 🟢 接口对接 |

---

## 2. 归因分析三要素

### 2.1 三要素定义

```
┌────────────────────────────────────────────────────────┐
│                   违规判定 #BAA-2026-0001               │
├────────────────────────────────────────────────────────┤
│  要素一：规范依据                                       │
│  ├── 国家标准: GB 50016-2014                            │
│  ├── 条款编号: 5.5.18                                   │
│  ├── 条款标题: 疏散楼梯净宽                             │
│  └── 规范原文: "高层公共建筑的疏散楼梯，其净宽度不应     │
│                小于1.2m。"                               │
├────────────────────────────────────────────────────────┤
│  要素二：参数证据                                       │
│  ├── 实体ID: ST-03                                     │
│  ├── 实体类型: staircase                               │
│  ├── 提取参数: clear_width                              │
│  ├── 提取值: 1.05m                                     │
│  ├── 提取方法: ezdxf_dimension_extraction              │
│  └── 置信度: 0.94                                      │
├────────────────────────────────────────────────────────┤
│  要素三：判定逻辑                                       │
│  ├── 操作符: >=                                        │
│  ├── 阈值: 1.2m                                        │
│  ├── 实际值: 1.05m                                     │
│  ├── 结果: FAIL                                        │
│  ├── 差值: -0.15m                                      │
│  └── 严重等级: major                                    │
├────────────────────────────────────────────────────────┤
│  附加：注意力热力图                                     │
│  ├── ST-03 (疏散楼梯): 0.87 ← 模型重点关注              │
│  ├── DR-07 (普通门): 0.12                              │
│  ├── EXIT-01 (安全出口): 0.01                           │
│  └── 说明: "模型重点关注ST-03，检测到净宽1.05m<1.2m"    │
├────────────────────────────────────────────────────────┤
│  💡 修改建议: 增加楼梯ST-03梯段宽度至≥1.2m              │
└────────────────────────────────────────────────────────┘
```

### 2.2 JSON输出结构

```json
{
  "finding_id": "BAA-2026-0001",
  "clause": {
    "standard": "GB 50016-2014",
    "clause_id": "5.5.18",
    "title": "疏散楼梯净宽",
    "text": "高层公共建筑的疏散楼梯，其净宽度不应小于1.2m。",
    "category": "fire_safety"
  },
  "extracted_params": {
    "entity_type": "staircase",
    "entity_id": "ST-03",
    "property_name": "clear_width",
    "extracted_value": 1.05,
    "unit": "m",
    "extraction_method": "ezdxf_dimension_extraction",
    "confidence": 0.94
  },
  "judgement": {
    "operator": ">=",
    "threshold": 1.2,
    "actual": 1.05,
    "result": "FAIL",
    "delta": -0.15,
    "severity": "major"
  },
  "attention_map": {
    "type": "rule_based",
    "focus_areas": [
      {"entity_id": "ST-03", "entity_type": "staircase", 
       "weight": 0.87, "reason": "目标实体（疏散楼梯）"},
      {"entity_id": "DR-07", "entity_type": "door", 
       "weight": 0.12, "reason": "关联实体（疏散门）"},
      {"entity_id": "EXIT-01", "entity_type": "exit", 
       "weight": 0.01, "reason": "关联实体（安全出口）"}
    ],
    "explanation": "模型重点关注了ST-03（疏散楼梯，注意力权重0.87），检测到净宽1.05m<1.2m。"
  },
  "explanation": "疏散楼梯ST-03的净宽度为1.05m，小于GB 50016-2014第5.5.18条要求的最小1.2m，差值为0.15m。",
  "suggestion": "建议将楼梯ST-03的梯段宽度增加至≥1.2m，或调整楼梯间布局以满足宽度要求。"
}
```

---

## 3. 注意力热力图（轻量级，非模型训练）

### 3.1 设计原则

| 原则 | 说明 |
|------|------|
| **规则标注，不训练模型** | 基于原子函数判定逻辑自动推导关注区域 |
| **权重分配透明可解释** | 每个图元的权重都有明确的规则依据 |
| **不增加推理时间** | 热力图在判定过程中附带生成，无额外计算 |

### 3.2 注意力权重分配规则

```python
def compute_attention_map(
    target_entity: Entity,
    related_entities: List[Entity],
    atomic_func: AtomicFunction
) -> AttentionMap:
    """
    基于规则计算注意力热力图
    
    权重分配逻辑：
    - 目标实体（判定对象）: 0.70-0.90
    - 直接关联实体（与目标有空间关系的实体）: 0.10-0.25
    - 间接关联实体（同一区域的其他实体）: 0.01-0.05
    - 无关实体: 0.00-0.01
    """
    focus_areas = []
    
    # 目标实体权重最高
    focus_areas.append(AttentionArea(
        entity_id=target_entity.id,
        entity_type=target_entity.type,
        weight=0.87,
        reason="目标实体（判定对象）"
    ))
    
    # 直接关联实体
    for entity in related_entities:
        if has_spatial_relation(target_entity, entity):
            weight = compute_spatial_weight(target_entity, entity)
            focus_areas.append(AttentionArea(
                entity_id=entity.id,
                entity_type=entity.type,
                weight=weight,
                reason=f"关联实体（{entity.type}）"
            ))
    
    # 归一化
    total = sum(a.weight for a in focus_areas)
    for area in focus_areas:
        area.weight = area.weight / total
    
    return AttentionMap(
        type="rule_based",
        focus_areas=focus_areas,
        explanation=build_attention_explanation(focus_areas)
    )
```

### 3.3 注意力热力图在前端的展示（DD-6对接）

```
┌──────────────────────────────────────────────────────┐
│  🔴 违规 #1 详细分析                                  │
│  ┌────────────────────┐ ┌────────────────────┐       │
│  │  注意力热力图        │ │  参数证据           │       │
│  │  [图元关注区域高亮]  │ │  • 提取: 净宽1.05m │       │
│  │  ST-03: ████████ 87%│ │  • 阈值: ≥1.2m     │       │
│  │  DR-07: ██       12%│ │  • 方法: ezdxf      │       │
│  │  EXIT-01: ▏       1%│ │  • 置信度: 0.94    │       │
│  └────────────────────┘ └────────────────────┘       │
│  📄 规范原文：第5.5.18条...                            │
│  💡 修改建议：增加梯段宽度至≥1.2m...                   │
└──────────────────────────────────────────────────────┘
```

---

## 4. 归因分析流程

### 4.1 完整流程

```
原子函数判定完成
    │
    ▼
┌─────────────────────┐
│  Step 1: 组装规范依据  │ ← 从规范JSON库读取条款信息
│  (clause)             │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Step 2: 提取参数证据  │ ← 从原子函数extract()结果
│  (extracted_params)   │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Step 3: 记录判定逻辑  │ ← 从原子函数judge()结果
│  (judgement)          │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Step 4: 计算注意力    │ ← 规则化推导关注区域
│  (attention_map)      │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Step 5: 生成说明+建议 │ ← 模板化生成
│  (explanation+fix)   │
└─────────┬───────────┘
          │
          ▼
      最终输出 (JSON)
```

### 4.2 代码接口

```python
def build_finding(
    atomic_func: AtomicFunction,
    param: ExtractedParam,
    judgement: Judgement,
    related_entities: List[Entity]
) -> Finding:
    """构建完整违规判定"""
    
    # Step 1: 规范依据
    clause = spec_repository.get_clause(atomic_func.clause_id)
    
    # Step 2-3: 参数证据+判定逻辑（直接从原子函数获取）
    
    # Step 4: 注意力热力图
    attention = compute_attention_map(param.entity, related_entities, atomic_func)
    
    # Step 5: 说明+建议
    explanation = build_explanation(clause, param, judgement)
    suggestion = build_suggestion(atomic_func, param, judgement)
    
    return Finding(
        finding_id=generate_id(),
        clause=clause,
        extracted_params=param,
        judgement=judgement,
        attention_map=attention,
        explanation=explanation,
        suggestion=suggestion
    )
```

---

## 5. 交付物清单

| 交付物 | 格式 | 说明 |
|--------|------|------|
| `finding_builder.py` | Python | 归因分析构建器 |
| `attention_computer.py` | Python | 注意力热力图计算（规则版） |
| `explanation_templates.py` | Python | 说明+建议模板 |
| `finding_schema.json` | JSON Schema | 归因输出格式定义 |

---

*编制：司军（AI业务助理）*
*日期：2026-06-09*
*参考论文#3 (Attribution) + #16 (Explainability)*
*决策依据：DD-06(三要素+轻量级热力图)*