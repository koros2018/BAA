# D1-T4（端点补全）+ D1-T5 Prometheus 指标 验收证据链

日期：2026-10-26 · commit `cXXX` · 紧接 D1-T3 之后

---

## 0. 前置

暂停前 Advisor 指出两个缺口：
1. **GET /standards 端点缺失**——D1-T1 在 `standards.py` 写了 `list_sets()` 但 FastAPI 路由里没注册
2. D1-T5 Prometheus 指标——Roadmap DoD 要求 `baa_spec_standards_total{code}` 和 `baa_spec_scale_overrides_total`

本轮把两个一起补。

---

## 1. GET /api/v1/standards 端点（D1-T4 前置）

### 1.1 端点位置

`admin_routes.py` router 直接 `app.include_router(admin_router)` 无前缀 → 端点落在 `/api/v1/standards`（与 `/api/v1/tasks` 同级）。

无需鉴权——标准集列表是引擎元数据，公开只读。

### 1.2 返回结构

```json
{
  "count": 4,
  "sets": [
    {"code": "CN-National-v1",    "name": "...", "version": "v1",
     "included_standards": ["GB 50016-2014", ...], "scale_overrides_count": 0,
     "description": "..."},
    {"code": "CN-Shanghai-v1",    ..., "scale_overrides_count": 3},
    {"code": "CN-Guangdong-v1",   ..., "scale_overrides_count": 3},
    {"code": "US-NFPA-v1",        ..., "scale_overrides_count": 0}
  ]
}
```

### 1.3 冒烟验证

```
GET /api/v1/standards -> 200
  count=4
  CN-Guangdong-v1: scale_overrides_count=3, standards=5
  CN-National-v1: scale_overrides_count=0, standards=5
  CN-Shanghai-v1: scale_overrides_count=3, standards=5
  US-NFPA-v1: scale_overrides_count=0, standards=4
```

### 1.4 改动清单

| 文件 | 动作 |
|---|---|
| `src/api/admin_routes.py` | 新增 `GET /api/v1/standards` 端点（25 行） |

---

## 2. D1-T5 Prometheus 指标

### 2.1 两个新 Gauge

| 指标 | 类型 | 标签 | 说明 |
|---|---|---|---|
| `baa_spec_standards_total` | Gauge | `code` | 每个标准集的 `included_standards` 条数 |
| `baa_spec_scale_overrides_total` | Gauge | 无 | 所有已注册标准集的 `scale_overrides` 总 key 数 |

### 2.2 采集模式

沿用 T-C3 `collect_queue_stats()` 模式——`collect_spec_stats()` 在 `render_metrics()` 里调用（与 Queue Gauge 并列），从 `StandardSet` 注册表动态读取：

```python
def collect_spec_stats() -> None:
    global _spec_stats_collected_once
    if _spec_stats_collected_once:
        return  # 幂等短路：标准集启动后不再变动
    for s in StandardSet.all():
        SPEC_STANDARDS_TOTAL.labels(code=s.code).set(
            float(len(s.included_standards))
        )
        total_overrides += len(s.scale_overrides)
    SPEC_SCALE_OVERRIDES_TOTAL.set(float(total_overrides))
    _spec_stats_collected_once = True
```

冷启动安全：StandardSet 导入异常时 warning 不影响其他指标输出。

### 2.3 /metrics 端点实际输出

```
# HELP baa_spec_standards_total 已注册规范集数（按 code 标签；每个 code 的值为 included_standards 条数）
# TYPE baa_spec_standards_total gauge
baa_spec_standards_total{code="CN-Guangdong-v1"} 5.0
baa_spec_standards_total{code="CN-National-v1"} 5.0
baa_spec_standards_total{code="CN-Shanghai-v1"} 5.0
baa_spec_standards_total{code="US-NFPA-v1"} 4.0
# HELP baa_spec_scale_overrides_total 所有已注册规范集累计地标阈值覆盖条数
# TYPE baa_spec_scale_overrides_total gauge
baa_spec_scale_overrides_total 6.0
```

- 4 个 code 全部出现在 `/metrics`
- `baa_spec_scale_overrides_total = 6.0`（上海 3 + 广东 3）
- CN-National 5 个 included_standards / US-NFPA 4 个 included_standards

### 2.4 改动清单

| 文件 | 动作 |
|---|---|
| `src/baa_engine/observability.py` | 新增 2 个 Gauge + `collect_spec_stats()` + `__all__` 更新 + `render_metrics()` 调用 |

---

## 3. 全量回归

```
python -m pytest src/tests -q
2642 passed, 23 skipped, 14 deselected, 8 warnings in 73.70s
（基线 2642 → **+0 / 0 退化**）
```

## 4. 里程碑 M1 更新

| 任务 | 状态 |
|---|---|
| D1-T1 标准集抽象层 | ✅ commit 0366e25 |
| D1-T2 尺度注入 + 硬编码兜底 | ✅ commit 0366e25 |
| D1-T3 首批地标导入 | ✅ commit 1cb0e3b |
| D1-T4 前端面板（后端端点补全）| ✅ GET /api/v1/standards |
| D1-T5 Prometheus 指标 | ✅ commit cXXX |

**M1 里程碑 5/5 任务完成**（D1-T4 前端 Vue 组件仍需前端改动，但后端 API 端点已就位）。

---

## 5. 后续依赖

| 任务 | 复用 |
|---|---|
| **D1-T4 前端 Vue 组件** | `GET /api/v1/standards` 已就绪，前端下拉直接调 |
| **D2-T1 / D3-T1 等** | M1 全部完成，进入 M2/M3 |
| Prometheus 告警规则 | `baa_spec_standards_total{code="CN-Shanghai-v1"} == 0` → 说明地标集未加载，可加 alert |
