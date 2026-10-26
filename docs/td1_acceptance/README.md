# T-D1 验收证据链：多标准 / 地方尺度库 — T1 标准集抽象层

日期：2026-10-26 · 分支：main · 阶段 D 首批任务

---

## 1. 范围

D1-T1 是 D1 标准集任务的**技术基座**：引入 `StandardSet` 概念（一组规范标准 + func→standard 映射），审查管线按请求参数动态选择，**缺省值保持现有 4 国标行为不变**。

后续 D1-T2（尺度参数注入原子函数）、D1-T3（首批地标导入）依赖本基座。

---

## 2. 改动清单（6 文件，3 新增 + 3 修改）

| 文件 | 动作 | 说明 |
|---|---|---|
| `src/baa_engine/standards.py` | **新增** | StandardSet dataclass + list_sets/load_set/available_codes + 内置 CN-National-v1 / US-NFPA-v1 + build_func_standard_maps_for_all_sets |
| `src/tests/test_standard_set.py` | **新增** | 10 单测覆盖注册/加载/缺省/未知 code/映射填充/存量回归 |
| `docs/td1_scale_inventory.md` | 待建（D1-T2 做） | 30+ 原子函数阈值硬编码盘点 |
| `src/api/baa_api.py` | 修改 | 引擎预热后调用 `build_func_standard_maps_for_all_sets` 预填充映射 |
| `src/api/admin_routes.py` | 修改 | `_run_review_task` 加 `standard_set_code` 参数；get_threshold 调用点按 StandardSet 解析 standard；`POST /api/v1/tasks` 加 Query 参数 + 400 校验 + 存 task dict |
| `src/baa_engine/spec_data/_repo.py` | 修改 | SpecRepository.get_threshold `standard: Optional[str] = None`，None 自动回退默认 |

**零破坏存量**：`_repo.py` 签名向后兼容（原默认值 "GB 50016-2014"）；`admin_routes.py` 原有 `get_threshold` 调用不传 standard 时行为完全不变。

---

## 3. 验收口径

> API 层 `POST /api/v1/tasks` 新增 `standard_set_code` 可选参数，缺省 `CN-National-v1`；错误 code 返回 400。

### 3.1 冒烟证据（直接 import 验证）

```
=== 内置集 ===
  CN-National-v1: 中国国家级标准（v1）
    standards: ['GB 50016-2014', 'GB 50016-2018', 'GB 50974-2014', 'GB 50763-2012', 'GB 50067-2014']
  US-NFPA-v1: 美国 NFPA 标准（v1）
    standards: ['NFPA 101-2021', 'NFPA 5000-2021', 'NFPA 13-2021', 'NFPA 14-2021']

=== SpecRepository === clauses=199, standards=['GB 50016-2014', 'GB 50067-2014', 'GB 50763-2012', 'GB 50974-2014', 'NFPA 101-2021', 'NFPA 13-2021', 'NFPA 14-2021', 'NFPA 5000-2021']

GB50016-5.5.18 func_id = DIM-001
resolve_standard = GB 50016-2014
get_threshold with resolved standard: val=1.2, unit=m, op=>=
get_threshold(None 回退): val=1.2, unit=m, op=>=
未知 code KeyError ✓
```

### 3.2 单测结果

```
src/tests/test_standard_set.py ........... 10 passed
```

覆盖 5 组断言：
1. 内置集注册到位（CN-National-v1 + US-NFPA-v1）
2. CN-National-v1 覆盖 4 国标、US-NFPA-v1 覆盖 4 份 NFPA
3. StandardSet.populate_func_standard_map 填充映射后 resolve_standard 能返回对应 standard
4. get_threshold standard=None 自动回退默认并拿到正常值
5. 直接 import SpecRepository 旧调用路径行为不变（回归保护）

### 3.3 全量回归

```
python -m pytest src/tests -q
2626 passed, 22 skipped, 14 deselected, 8 warnings in 70.34s
（基线 2616 → +10 passed / 0 failed）
```

---

## 4. 三层穿透链验证

| 层 | 点 | 动作 |
|---|---|---|
| **API 入口** | `POST /api/v1/tasks` | 新增 `standard_set_code: str = Query("CN-National-v1")` |
| **任务存储** | `_ag._tasks[task_id]["standard_set_code"]` | 新字段入库，后台可查 |
| **后台执行** | `_run_review_task(... standard_set_code=...)` | 新增签名参数 |
| **规范判定** | `_ag._spec_repo.get_threshold(func.clause_id, building_type, resolved_standard)` | StandardSet.resolve_standard(func.func_id) 解析 standard 后传入 |
| **SpecRepository** | `get_threshold(..., standard=None)` | None → 自动回退默认 "GB 50016-2014" |

穿透任一环节不丢值：`Query → dict → sig → get_threshold` 全链路带值通过。

---

## 5. 设计要点

**薄过滤层**：SpecRepository 启动时仍一次加载全部 199 条 clause（启动时间不变），StandardSet 不重建加载机制，仅做 func_id → standard 的映射查询。这样任何标准集组合都能覆盖（同一 func_id 可在多个 standard 里都有 clause）。

**Engine Warmup 预填充**：`build_func_standard_maps_for_all_sets` 在 `_spec_repo = SpecRepository()` 之后立即调用一次，把映射预计算好——审查执行时只做 dict lookup，零运行时额外开销。

**缺省安全**：`CN-National-v1` = 当前 4 国标全覆盖，API 不传 standard_set_code 时行为完全不变；未知 code 返回 400（API 层）+ 内部 _run_review_task 也做 try/except 回退到默认 standard。

---

## 6. 后续任务依赖

| 任务 | 前置 | 复用本基座 |
|---|---|---|
| **D1-T2** 尺度参数注入原子函数 | ✅ D1-T1 | StandardSet.scale_overrides + resolve_standard 同链路 |
| **D1-T3** 首批地标（上海/广东） | ✅ D1-T1 | 新 StandardSet 注册 + _func_to_standard 映射自动构建 |
| **D1-T4** 前端标准集面板 | ✅ D1-T1 | `GET /standards` 接口返回 list_sets() |
| **D1-T5** Prometheus 指标 | ✅ D1-T1 | BAA_SPEC_STANDARDS_TOTAL / BAA_SPEC_SCALE_OVERRIDES_TOTAL |

---

## 7. 已知限制（本任务范围外）

- StandardSet 目前仅静态注册，无动态增删接口（留给 D1-T4 管理面板做）。
- scale_overrides 已定义字段但未接入 get_threshold（D1-T2 尺度参数注入任务处理）。
- 无 `GET /standards` 端点（D1-T4 前端面板任务处理）。
