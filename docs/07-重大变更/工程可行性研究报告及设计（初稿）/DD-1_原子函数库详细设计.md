# DD-1：原子函数库——详细设计文档

> **所属阶段：** 工程设计（详细设计）
> **对应架构层：** 核心推理层
> **编制日期：** 2026-06-09
> **批准依据：** Master批准（决策DD-01: 30个原子函数, DD-10: AND/OR/NOT三算子）
> **前提约束：** 结构一次搭好，框架预留扩展位

---

## 1. 设计概述

### 1.1 设计目标

构建BAA规范判定原子函数库，参考论文#1 (LLM-FuncMapper)的66个原子函数体系，框架预留30个位置覆盖6类判定，首批实现10个。

**核心指标（终稿定稿，2026-06-20）：**
- 原子函数框架：**30个**（6类判定各预留3-6个）
- **首批实现：10个**（与规范JSON库10条L1级对齐）
- 判定准确率：**100%**（L1级原子函数）
- 复合判定：支持**AND/OR/NOT**三算子

### 1.2 参考来源

| 参考来源 | 贡献 | 复用程度 |
|---------|------|---------|
| 论文#1 (LLM-FuncMapper) | 66个原子函数体系定义 | 🟢 体系参考 |
| 可研报告v3.0 | 架构四层定义 | 🟢 约束条件 |
| DD-4 图纸解析管线 | 结构化图纸数据输入格式 | 🟢 接口对接 |

---

## 2. 原子函数体系

### 2.1 6类原子函数

| 函数类别 | 标识前缀 | 示例 | 对应的BAA规范条款 |
|---------|---------|------|-----------------|
| 尺寸判定类 | AF-DIM | `check_dimension(entity, prop, op, threshold)` | 疏散宽度、房间面积、净高 |
| 距离判定类 | AF-DIST | `check_distance(entity_a, entity_b, op, threshold)` | 疏散距离、防火间距 |
| 存在性判定类 | AF-EXIST | `check_existence(layer, entity_type, required)` | 防火门、疏散指示标志 |
| 计数判定类 | AF-COUNT | `check_count(layer, entity_type, op, threshold)` | 安全出口数量、消防电梯数量 |
| 属性判定类 | AF-ATTR | `check_attribute(entity, attr, op, value)` | 防火门等级、材料燃烧等级 |
| 关系判定类 | AF-REL | `check_relation(entity_a, rel, entity_b)` | 楼梯间通往、防火分区连通 |

### 2.2 30个原子函数分配计划

| 类别 | 计划数量 | 首批实现 | 预留 | 说明 |
|------|:-------:|:-------:|:----:|------|
| AF-DIM | 6 | 3 | 3 | 宽度/面积/高度 |
| AF-DIST | 5 | 2 | 3 | 疏散距离/防火间距 |
| AF-EXIST | 6 | 3 | 3 | 防火门/楼梯间/消防设施 |
| AF-COUNT | 5 | 2 | 3 | 出口数量/电梯数量 |
| AF-ATTR | 5 | 2 | 3 | 防火门等级/材料等级 |
| AF-REL | 3 | 1 | 2 | 防火分区连通关系 |

### 2.3 首批10个原子函数清单

| 函数ID | 名称 | 类别 | 对应规范 | 输入参数 | 输出 |
|--------|------|------|---------|---------|------|
| AF-DIM-001 | 疏散楼梯净宽判定 | 尺寸 | GB50016-5.5.18 | 楼梯ID, 阈值1.2m | PASS/FAIL + 差值 |
| AF-DIM-002 | 防火分区面积判定 | 尺寸 | GB50016-6.1.1 | 分区ID, 阈值2500㎡ | PASS/FAIL + 差值 |
| AF-DIM-003 | 消防车道宽度判定 | 尺寸 | GB50016-7.1.1 | 车道ID, 阈值4m | PASS/FAIL + 差值 |
| AF-DIST-001 | 疏散距离判定 | 距离 | GB50016-5.5.17 | 起点ID, 终点ID, 阈值30m | PASS/FAIL + 差值 |
| AF-EXIST-001 | 安全出口存在判定 | 存在 | GB50016-5.5.8 | 区域ID, 出口类型 | PASS/FAIL |
| AF-EXIST-002 | 楼梯间设置判定 | 存在 | GB50016-5.5.12 | 建筑高度, 楼梯类型 | PASS/FAIL |
| AF-EXIST-003 | 自动喷水系统判定 | 存在 | GB50016-8.3.3 | 建筑类型, 面积 | PASS/FAIL |
| AF-COUNT-001 | 安全出口数量判定 | 计数 | GB50016-5.5.8 | 区域ID, 阈值2 | PASS/FAIL |
| AF-ATTR-001 | 防火门等级判定 | 属性 | GB50016-6.5.1 | 门ID, 等级要求"甲" | PASS/FAIL |
| AF-REL-001 | 防火分区连通判定 | 关系 | GB50016-6.2.9 | 分区A, 分区B, 隔墙类型 | PASS/FAIL |

---

## 3. 基类设计

### 3.1 原子函数基类

```python
class AtomicFunction:
    """
    原子函数基类
    每个原子函数封装：
    1. 几何参数提取逻辑（从结构化图纸数据中提取所需参数）
    2. 规范阈值判定（与阈值比较）
    3. 违规报告生成（附带归因分析）
    4. 注意力热力图贡献（告知模型关注了什么图元）
    """
    id: str           # 唯一标识，如 "AF-DIM-001"
    name: str         # 中文名称，如 "疏散楼梯净宽判定"
    category: str     # 类别: dimension / distance / existence / count / attribute / relation
    params: dict      # 参数定义 {param_name: ParamSpec}
    
    def extract(self, drawing_data: StructuredDrawing) -> ExtractedParam:
        """从结构化图纸数据中提取判定所需参数"""
        pass
    
    def judge(self, param: ExtractedParam) -> Judgement:
        """执行规范阈值判定，返回判定结果"""
        pass
    
    def explain(self, judgement: Judgement) -> Explanation:
        """生成可解释的违规说明（含归因三要素）"""
        pass
    
    def get_attention(self, param: ExtractedParam) -> AttentionMap:
        """返回判定过程中关注的图元及权重（DD-3归因热力图）"""
        pass
```

### 3.2 参数定义规范

```python
@dataclass
class ParamSpec:
    """参数定义"""
    name: str            # 参数名
    type: str            # 类型: dimension / count / boolean / enum
    unit: str | None     # 单位: m / ㎡ / 个 / None
    description: str     # 中文说明
    
@dataclass
class ExtractedParam:
    """提取的参数值"""
    entity_id: str                # 实体ID
    entity_type: str              # 实体类型
    property_name: str            # 属性名
    value: float | int | str      # 提取值
    unit: str | None              # 单位
    confidence: float             # 置信度 0-1
    extraction_method: str        # 提取方法描述
    attention_weight: float       # 注意力权重（DD-3用）
```

### 3.3 判定结果规范

```python
@dataclass
class Judgement:
    """判定结果"""
    operator: str                 # 操作符: >= / <= / > / < / == / != / exists
    threshold: float | int | str  # 阈值
    actual: float | int | str     # 实际值
    result: str                   # PASS / FAIL / SKIP
    delta: float | None           # 差值（仅FAIL时）
    severity: str                 # critical / major / minor / info

@dataclass  
class Explanation:
    """归因说明（DD-3三要素）"""
    clause: dict                  # 规范依据: {standard, clause_id, title, text}
    params: ExtractedParam        # 参数证据
    judgement: Judgement          # 判定逻辑
    suggestion: str               # 修改建议
```

### 3.4 复合判定

```python
def AND(*checks: Judgement) -> Judgement:
    """所有检查必须通过"""
    failed = [c for c in checks if c.result == 'FAIL']
    if failed:
        return Judgement(result='FAIL', detail=failed)
    return Judgement(result='PASS')

def OR(*checks: Judgement) -> Judgement:
    """任一检查通过即可"""
    passed = [c for c in checks if c.result == 'PASS']
    if passed:
        return Judgement(result='PASS')
    return Judgement(result='FAIL')

def NOT(check: Judgement) -> Judgement:
    """取反"""
    return Judgement(
        result='PASS' if check.result == 'FAIL' else 'FAIL',
        operator=check.operator,
        threshold=check.threshold,
        actual=check.actual
    )

# 使用示例
def check_evacuation_stair():
    return AND(
        check_stair_width(...),    # AF-DIM-001: 楼梯净宽≥1.2m
        check_exit_count(...),     # AF-COUNT-001: 安全出口≥2个
        check_exit_distance(...),  # AF-DIST-001: 疏散距离≤30m
        NOT(check_door_blocked())  # AF-EXIST-001: 门未堵塞
    )
```

---

## 4. 注册与发现

### 4.1 函数注册表

```python
# atomic_function_registry.py

from typing import Dict

class AtomicFunctionRegistry:
    """原子函数注册表"""
    _functions: Dict[str, AtomicFunction] = {}
    
    @classmethod
    def register(cls, func: AtomicFunction):
        cls._functions[func.id] = func
    
    @classmethod
    def get(cls, func_id: str) -> AtomicFunction:
        return cls._functions[func_id]
    
    @classmethod
    def list_by_category(cls, category: str) -> list:
        return [f for f in cls._functions.values() if f.category == category]
    
    @classmethod
    def list_by_clause(cls, clause_id: str) -> list:
        """返回某条规范对应的所有原子函数"""
        return [f for f in cls._functions.values() 
                if clause_id in f.params.get('clauses', [])]
    
    @classmethod
    def all(cls) -> Dict[str, AtomicFunction]:
        return cls._functions
```

### 4.2 首批注册示例

```python
# 注册AF-DIM-001: 疏散楼梯净宽判定
AtomicFunctionRegistry.register(StairWidthCheck())

# 注册AF-DIM-002: 防火分区面积判定
AtomicFunctionRegistry.register(FireZoneAreaCheck())

# 注册AF-COUNT-001: 安全出口数量判定
AtomicFunctionRegistry.register(ExitCountCheck())
# ...
```

---

## 5. 交付物清单

| 交付物 | 格式 | 说明 |
|--------|------|------|
| `atomic_function.py` | Python | 基类+参数规范+判定结果 |
| `atomic_function_registry.py` | Python | 注册表 |
| `functions_dim.py` | Python | 尺寸类原子函数（6个） |
| `functions_dist.py` | Python | 距离类原子函数（5个） |
| `functions_exist.py` | Python | 存在类原子函数（6个） |
| `functions_count.py` | Python | 计数类原子函数（5个） |
| `functions_attr.py` | Python | 属性类原子函数（5个） |
| `functions_rel.py` | Python | 关系类原子函数（3个） |
| `composite.py` | Python | AND/OR/NOT复合算子 |

---

*编制：司军（AI业务助理）*
*日期：2026-06-09*
*参考论文#1 (LLM-FuncMapper) 66原子函数体系*
*决策依据：DD-01(30个) + DD-10(AND/OR/NOT)*