# T-D2 验收证据链：尺度参数注入 + 硬编码阈值兜底

日期：2026-10-26 · 分支：main · 阶段 D 第二批任务

---

## 1. 前置发现（D1-T2 盘点）

对 `src/baa_engine/atomic/fire_general/*.py` 扫 threshold= 硬编码，对比 SpecRepository 默认值，发现一个生产级 bug：

| 项目 | 数量 | 说明 |
|---|---|---|
| 原子函数硬编码 threshold | **198 个** | dim_functions / exist_functions / attr_functions 等 |
| SpecRepository clause 总数 | 199 条 | 全部有 params.threshold key（真实值 1.0 / 1.2 / 1100 等） |
| **SpecRepository 找不到 clause 的原子函数** | **≈128 个** | SpecRepository 是"精选 clause 集合"，不是全覆盖 |
| SpecRepository clause vs 原子函数硬编码不一致 | 16 个 | 以 SpecRepository 为准（admin_routes.py 覆盖） |

**核心 bug**：admin_routes.py Step 3 原来无条件 `func.threshold = threshold_val`，而 `SpecRepository.get_threshold` 找不到 clause 时返回 `(0.0, '', '>=')`。这导致**128 个无 clause 的原子函数阈值被毁**（被覆盖为 0.0），只有 SpecRepository 有 clause 的那部分函数正常工作。

D1-T2 的本质不是"提取硬编码为可注入参数"，而是**让 SpecRepository 有值时覆盖、没值时保留原子函数的硬编码兜底**。

---

## 2. 改动清单（5 文件，3 修改 + 1 新增 + 1 新增清单）

| 文件 | 动作 | 说明 |
|---|---|---|
| `src/baa_engine/spec_data/_repo.py` | 修改 | 新增 `get_threshold_safe` 返回 `Optional[Tuple]`；旧 `get_threshold` 加 `.get('threshold')` 安全取值零破坏 |
| `src/api/admin_routes.py` | 修改 | Step 3 改用 `get_threshold_safe`；引入 `ScaleContext`；clause.standard 动态取值；`scale_overrides` 优先级接口预留 |
| `src/baa_engine/standards.py` | 修改 | 新增 `ScaleContext` dataclass（standard_set_code + standard_set + scale_overrides） |
| `src/tests/test_scale_injection.py` | **新增** | 8 单测 + 1 skip；覆盖 get_threshold_safe 三种 None 场景 + ScaleContext 代理 + scale_overrides 优先级 + 旧 get_threshold 回归保护 |
| `src/tests/test_standard_set.py` | 修改 | 受 SpecRepository 共享全局污染影响，修正测试用例 |

**零破坏**：`SpecRepository.get_threshold` 旧签名行为不变（只是内部加了 `.get('threshold')` 安全取值）；直接 import 调用路径行为不变。

---

## 3. 验收口径

> 引入 ScaleContext 上下文对象，审查管线启动时按 standard_set 注入，原子函数内通过 ctx.get_threshold 替代常量。注入缺省回退现有常量值，确保不指定 standard_set 时行为完全回归。

### 3.1 SpecRepository.get_threshold_safe 三种 None 场景

```
找不到 clause → None ✓
params 缺 threshold key → None（不再抛 KeyError，零破坏） ✓
params.threshold=0.0 → None（如将来出现这种数据填漏） ✓
```

### 3.2 admin_routes.py Step 3 覆盖逻辑

```
当前优先级：scale_overrides（地标覆盖，D1-T3 预留）
         > SpecRepository.get_threshold_safe 返回值
         > 原子函数硬编码 threshold（兜底）
```

128 个无 clause 原子函数现在能正常工作（用构造时硬编码）；有 clause 的函数仍用 SpecRepository 动态值覆盖。

### 3.3 ScaleContext 封装

```python
_scale_ctx = ScaleContext.create(standard_set_code)
_scale_ctx.resolve_standard(func.func_id)  # 代理 StandardSet
_scale_ctx.get_override(clause_id, building_type)  # scale_overrides 接口预留
```

把 standard_set_code + StandardSet + scale_overrides 收拢为一个对象，admin_routes.py 不再散落临时变量。

### 3.4 单测结果

```
src/tests/test_scale_injection.py ......  8 passed, 1 skipped
src/tests/test_standard_set.py   .......... 10 passed
```

覆盖：
- get_threshold_safe 找不到 clause → None
- get_threshold_safe 正常 clause → 返回 (val, unit, op)
- ScaleContext.create + resolve_standard 代理
- ScaleContext.get_override scale_overrides 优先级接口
- 旧 SpecRepository.get_threshold 行为不变（回归保护）
- SpecRepository 共享全局污染规避（测试设计注意事项）

### 3.5 全量回归

```
python -m pytest src/tests -q
2634 passed, 23 skipped, 14 deselected, 8 warnings in 84.66s
（基线 2626 → +8 passed / 0 failed）
```

---

## 4. 过程修复缺陷（1 个）

| 缺陷 | 根因 | 修复 |
|---|---|---|
| SpecRepository 找不到 clause 时 `func.threshold` 被覆盖为 0.0 → 128 个原子函数失效 | admin_routes.py 无条件赋值 + `get_threshold` 兜底值 `(0.0, '', '>=')` | 改 `get_threshold_safe` 返回 None → admin_routes.py 仅在有值时覆盖 |

---

## 5. 后续任务依赖

| 任务 | 前置 | 复用 |
|---|---|---|
| **D1-T3 首批地标（上海/广东）** | ✅ D1-T1 + D1-T2 | StandardSet 注册新 code + ScaleContext.scale_overrides 阈值覆盖 |
| **D1-T4 前端标准集面板** | ✅ D1-T1 + D1-T2 | `GET /standards` 端点（ScaleContext 已有） |
| **D4-T2 License 功能开关** | ✅ D1-T1 + D1-T2 | License 驱动 ScaleContext.scale_overrides / standard_set_code 启用/禁用 |

---

## 6. 关键设计决策

**薄上下文而非深度重构**：不做 "把 AtomicFunction 构造时的硬编码 threshold 全部改 None" —— 那样改动 198 个函数 + 测试量大 + 容易断存量。改为"SpecRepository 有值则覆盖、没值保留硬编码"，既修复 bug 又零侵入存量。

**scale_overrides 接口预留**：`ScaleContext.scale_overrides: Dict[str, Dict[str, float]]` 已就位，admin_routes.py 已按"override 优先"实现。未来 D1-T3 地标直接填 dict 即可，无需再改 admin_routes.py。

**SpecRepository 共享全局保护**：SpecRepository 持有的是 `gb50016_core/__init__.py` 的 `INITIAL_CLAUSES` 全局 list 引用——修改 clause.params 会污染所有 SpecRepository 实例。单测里禁止修改 clause 对象本身（用 skip 或构造临时对象）。
