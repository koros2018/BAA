# 03 · 关键类与函数说明

本分册详解引擎层的核心类、数据结构与关键方法。所有引用均可通过相对路径在源码中定位。

---

## 1. 图纸解析

### 1.1 `DrawingParser` — `src/baa_engine/drawing_parser.py`

图纸解析总入口，负责格式分发、分页提取、缓存与结果装配。

**常量**
- `SUPPORTED_FORMATS = {".dxf", ".dwg", ".pdf"}`
- `LARGE_FILE_MB = 50`、`MEMORY_LIMIT_MB = 1500`、`PAGE_SIZE = 5000`、`MAX_PAGES = 20`

**数据结构**
- `RawPrimitive`：图元原始记录 —— `dxf_type` / `layer` / `handle` / `bbox` / `properties`
- `DrawingResult`：解析结果总容器 —— `primitives`、`dimensions`、`error`、`warning`、
  `sheets`(P73)、`drawing_type`(P121)、`corrupt`(P121)、`block_refs`(P127-S1)；
  属性 `success = (error is None)`

**核心方法**
| 方法 | 说明 |
| --- | --- |
| `parse(path)` | 按文件 sha256 缓存命中则返回；否则按扩展名分发：`_parse_dwg` / `pdf_to_dxf` / `ezdxf.readfile`，随后 `_extract_primitives_paged` 分页提取，最后 `classify_drawing` 与 `is_likely_corrupt` 判定 |
| `_parse_dwg` | 委托 `parsers/dwg_convert.py`；失败时 `_detect_dwg_format` 给出天正 T3 / LibreCAD 提示 |
| `_extract_primitives_paged` | 分页遍历实体，控制内存上限 |

### 1.2 DWG 转换 — `src/baa_engine/parsers/dwg_convert.py`

**六级兜底链**（按顺序尝试）：
1. `_try_same_dir_dxf` — 同目录已存在的 DXF
2. `_try_librecad_convert` — LibreCAD 命令行转换
3. `_try_aspose_cad_convert` — Aspose.CAD 转换
4. `_try_ezdwg_export_dxf` — `ezdwg.read` + `export_dxf`（纯 Python）
5. `_try_manual_convert` — 手动转换
6. `_try_raw_decode` — 原始解码

辅助：`_detect_dwg_format`、`_resolve_xref_external`、`_parse_dwg`、`_insert_block_expand`。

### 1.3 PDF 矢量解析 — `src/baa_engine/parsers/pdf_parser.py`

`pdf_to_dxf(pdf_path)`：用 PyMuPDF (`fitz`) 提取矢量绘制指令，转换为 ezdxf 实体；
坐标单位 `pt → mm`（`× scale`）；`_extract_scale` 推断比例，`_bezier_to_lines[_scaled]` 将贝塞尔曲线离散为折线。

### 1.4 块引用提取 — `src/baa_engine/parsers/block_refs.py`

保留块名与属性的语义信息（避免块展平丢失语义）。

- `BlockRef`（`to_dict`）：块引用结构（块名、插入点、缩放、旋转、属性表）
- `read_block_ref` / `extract_block_refs` / `summarize_block_refs`
- `_as_xy` / `_first_attr` / `extract_attribs`：属性解析辅助

### 1.5 几何工具 — `src/baa_engine/parsers/geometry.py`

`compute_bbox`（含 TEXT/MTEXT 支持，P128）、`extract_properties`、`compute_polygon_area`、`transform_point`。

### 1.6 天正 T3 — `src/baa_engine/tianzheng_t3.py`

- `Component`（L170）：天正构件
- `TianzhengT3`（L229）：解析入口，覆盖 T3 加密 / T0 明文 / 自定义对象 XData 三类存储形态

### 1.7 图纸分类 — `src/baa_engine/drawing_classifier.py`

- `classify_drawing(...)` → `{type, confidence, reason, suggested_action}`（结构/电气/暖通 = 非建筑图）
- `is_likely_corrupt(...)` → `{corrupt, reason, recoverable}`

---

## 2. 语义分析 — `src/baa_engine/semantic_analyzer/`

### 2.1 数据结构 — `models.py`

- `SemanticEntity`：`id` / `type` / `bbox` / `layer` / `subtype` / `confidence` / `properties`（`to_dict`）
- `SpatialRelation`：`source_id` / `target_id` / `type`（`adjacent` | `contains` | `connects_to`）/ `distance` / `via` / `confidence`

### 2.2 `SemanticAnalyzer` — `main.py`

常量：`ADJACENT_THRESHOLD = 50.0`（mm）；内部 `_analyze_cache` 指纹缓存。

**`analyze(primitives, dimensions, max_entities=10000, building_type="civil", dxf_path=None)`** 流水线：

| 步骤 | 方法 | 说明 |
| --- | --- | --- |
| 缓存 | — | 指纹缓存命中直接返回 |
| Step1 | `_classify_entities` | 按图层规则 / 几何特征分类实体 |
| Step1.05 | `_detect_floor_levels` / `_assign_entities_to_floors` | 楼层识别与归属（P35） |
| Step1.1 | `_yolo_enhance` / `_merge_yolo_results` | YOLO 设备增强（可选） |
| Step1.4 | `_sweep_line_detect_rooms` | 扫线法房间检测（使用全量 primitives） |
| Step1.5 | `_infer_corridor_widths` | 走廊宽度推断（平行线聚类 + bbox 短边） |
| Step1.6 | — | 门 / 防火门宽度与防火等级推断 |
| Step2 | `_build_relations` | 构建空间关系 |
| Step2.1 | `_infer_room_types` | 房间类型推断（P109） |
| Step3 | `_bind_dimensions` | 尺寸标注绑定到实体 |
| Step4 | `build_corridor_topology` | 走廊拓扑 |
| Step5 | `analyze_evacuation_routes` | 疏散路径分析 |
| Step5.3 | `verify_evacuation_connectivity` | 疏散连通性校验（P33） |

**返回结构**：`{entities, relations, attributes, building_type, corridor_topology,
evacuation_routes, evacuation_connectivity, floor_levels, floor_assignments}`

**委派方法**（实现在子模块）：`_classify_by_layer` / `_classify_by_geometry` / `_parse_meta_entities` /
`_is_near_closed` / `_merge_overlapping` / `_infer_attribute_name` / `_merge_line_chains_to_rooms`。

### 2.3 语义子模块

| 文件 | 关键内容 |
| --- | --- |
| `layer_rules.py` | 聚合 8 个 `_layer_rules_*` 分片，导出 `LAYER_RULES` / `SHORT_LAYER_RULES`（分片详解见 §2.4） |
| `classify.py` | 实体分类：`_classify_by_layer`（图层规则）/ `_classify_by_geometry`（几何兜底）/ `_classify_entities`（总装配） |
| `room.py` | `_is_near_closed` / `_sweep_line_detect_rooms`；上游含**图框与表格区域排除**（P130），避免图例表被误识别为房间 |
| `relations.py` | `_build_relations` / `_bind_dimensions` / `_infer_attribute_name` |
| `merge.py` | 实体合并 |
| `meta.py` | META 实体解析 |
| `enhancement.py` | YOLO 增强接入 |
| `evacuation.py` | `_build_corridor_topology_impl` / `_analyze_evacuation_routes_impl` / `_verify_evacuation_connectivity_impl` |
| `room_type_infer.py` | `infer_room_type` |
| `geometry.py` | `compute_iou` / `union_bbox` / `min_edge_distance` / `is_inside` / `bbox_center` / `point_distance` |

### 2.4 图层规则（Layer Rules）分片详解

图层规则是语义识别的**第一道关口**：把 DXF 图层名映射为实体语义类型（wall / door / sprinkler …）。
规则被打散为 **8 个 `LAYER_RULES_*` 分片 + 1 个 `SHORT_LAYER_RULES` 分片**，由 `layer_rules.py` 聚合。

#### 2.4.1 聚合机制 — `layer_rules.py`

```python
LAYER_RULES = _merge_dicts(
    LAYER_RULES_CORE,      # 1 基础建筑构件
    LAYER_RULES_FIRE,      # 2 消防设施
    LAYER_RULES_P70_FREQ,  # 3 P70 高频缺口 1-4 批
    LAYER_RULES_P74,       # 4 P74 准确率专项
    LAYER_RULES_P70_B5,    # 5 P70 缺口第 5 批 + 最终
    LAYER_RULES_P70_TAIL,  # 6 P70 尾批（2-ref）
    LAYER_RULES_STRUCT,    # 7 结构/非建筑/电气
    LAYER_RULES_P79,       # 8 P79 真实图纸 + P47 无障碍 + P70 Final
)
```

- `_merge_dicts` 使用 `dict.update` 逐片合并：**后加载分片覆盖同键的先前值**，且键的迭代顺序保留首次插入位置。
  因此**分片顺序即匹配优先级顺序**，同键冲突时以最后一片为准。
  例：`"车位"` 在 P74 定义为 `parking_spot`、在 P79 覆盖为 `parking_space`；`"ELEVATOR"` 在 P70_FREQ 为 `elevator`、在 P79 覆盖为 `accessible_elevator`。
- `SHORT_LAYER_RULES` 是**独立字典，不参与合并**，单独在第二轮匹配。

#### 2.4.2 两类匹配策略 — `classify.py::_classify_by_layer`

| 规则集 | 关键字长度 | 匹配方式 |
| --- | --- | --- |
| `LAYER_RULES` | ≥3 字符 | **子串匹配**（`keyword in layer_upper`），覆盖全部 8 个分片 |
| `SHORT_LAYER_RULES` | 1–2 字符 | **全词匹配**：命中位置前需为 `_` 或字符串开头，后需为 `_` 或字符串结尾 |

匹配流程：图层名先 `upper()` → 先按 `LAYER_RULES` 子串扫描，命中即返回；未命中再按
`SHORT_LAYER_RULES` 做全词扫描；仍未命中返回 `"unknown"`。
`_classify_entities` 随后对 `unknown` / `other` 走 `_classify_by_geometry` 几何兜底。

> 长/短分离是为**抑制误命中**：1–2 字符规则若也做子串匹配会大量误伤。
> 典型修复：裸 `"L"` 被移除（曾把 `WP_L_PJ` 水管道层误判为 lobby），
> `"T"`（通信层）、`"W"`/`"D"`/`"C"`/`"ST"` 等改为全词匹配。

#### 2.4.3 分片职责与规模

下表为实测数据：**行数**为该分片源文件行数，**键数**为该分片字典的唯一键数量。

| 分片文件 | 行数 | 键数 | 合并顺序 | 覆盖主题 |
| --- | --- | --- | --- | --- |
| `_layer_rules_core.py`（`LAYER_RULES_CORE`） | 43 | 37 | 1 | 墙/门/窗/楼梯/走廊/防火分区/尺寸/出口/防火门/消防电梯/设备（含 BEAM/COLUMN→wall） |
| `_layer_rules_fire.py`（`LAYER_RULES_FIRE`） | 26 | 20 | 2 | 真实图纸消防设施层：消火栓、喷淋阀、FAS-、VESDA、消防泵、启泵、水泵接合器等 |
| `_layer_rules_p70_freq.py`（`LAYER_RULES_P70_FREQ`） | 155 | 138 | 3 | P70 高频缺口 1–4 批：探测器、楼层、泵房、防火卷帘、避难层/区/间、风管、幕墙、电梯等 |
| `_layer_rules_p74.py`（`LAYER_RULES_P74`） | 102 | 78 | 4 | P74 准确率专项（16 图审计）：英文缩写变体（HYDR/SPRK/SMOKE_DET）、天正/南方 CAX 前室变体、无障碍门/电梯、停车位等 |
| `_layer_rules_p70_b5.py`（`LAYER_RULES_P70_B5`） | 130 | 124 | 5 | P70 缺口第 5 批 + 最终批：无障碍房间、疏散门/标志、救援口、布线、发电机、幕墙玻璃、防火单元/分隔等 |
| `_layer_rules_p70_tail.py`（`LAYER_RULES_P70_TAIL`） | 235 | 222 | 6 | P70 尾批（2-ref 类型）：房间功能（病房/教室/KTV/舞厅）、结构（承台/桩/楼板）、无障碍设施、疏散设施、给排水等 |
| `_layer_rules_struct.py`（`LAYER_RULES_STRUCT`） | 45 | 39 | 7 | 结构基础（BASE→foundation）+ 非建筑实体（HATCH/AXIS/钢筋→other）+ 电气设备 + 消防设施 |
| `_layer_rules_p79.py`（`LAYER_RULES_P79`） | 157 | 146 | 8 | P79 真实图纸补全：暖通 HVAC 分层、图框/标题块、规划/绿化、轴网、P47 无障碍、坐标/面积标注等 |
| `_layer_rules_short.py`（`SHORT_LAYER_RULES`，独立不合并） | 100 | 90 | — | 短关键字（1–2 字符）全词匹配：W/D/M/C/ST/FZ/FD/FE/T + P34 电气扩展 + P70 Final 低频项（ACCESS_ROAD/NOZZLE/…） |

> **规模与去重**：8 个长关键字分片键数之和为 **804**，经 `_merge_dicts` 覆盖去重后
> `LAYER_RULES` 实测 **748** 个键（约 56 个键被后置分片覆盖）；
> `SHORT_LAYER_RULES` 为独立字典，实测 **90** 个键，不参与上述合并。

#### 2.4.4 与既有分片的衔接与扩充约定

- **只加不改**：新增图层映射应写入**当前活跃批次对应的分片**（如真实图纸补全写入 `_layer_rules_p79.py`），
  避免触碰其他主题分片而引入回归。
- **新增分片**：若需另起主题分片，须在 `_layer_rules_core.py` 同级的 `layer_rules.py` 中 import 该分片，
  并追加到 `_merge_dicts(...)` 参数列表末尾——**位置决定优先级**，越靠后优先级越高。
- **短关键字单列**：1–2 字符规则必须写入 `SHORT_LAYER_RULES`（走全词匹配），
  不得混入长分片（长分片一律子串匹配，会造成大面积误命中）。
- **冲突排查**：定位某图层类型的来源时，可按分片合并顺序自后向前查找，命中位置即当前生效分片。

#### 2.4.5 与其他模块的衔接

- 规则只负责**图层名 → 类型**；几何形状判据（闭合多边形/圆弧/半径阈值）在 `classify.py::_classify_by_geometry`，
  文字关键词（TEXT）与块名（INSERT）映射同样在 `classify.py`。
- 图层规则返回 `other` 的图元会被几何兜底“挽留”为 `wall`（P80/P82 修复），避免闭合房间被误杀导致疏散分析为空；
  但仅接受 `wall`，以防填充层（PUB_HATCH）的短 LINE 被误判为 door。

### 2.5 尺寸解析 — `src/baa_engine/dimension_parser.py`

`DimensionParser`（L28）：`extract_dimensions`（提取标注）、`inject_into_entities`（注入实体属性）。

---

## 3. 原子函数体系 — `src/baa_engine/atomic_functions.py`

### 3.1 枚举与数据结构

**`FuncCategory`**：`DIMENSION="dim"` / `COUNT` / `DISTANCE="dist"` / `ATTR` / `EXIST` / `AREA` /
`EVAC` / `ACCESS` / `LIGHT` / `THERMAL` / `STRUCTURAL`

**`Severity`**：`CRITICAL` / `MAJOR` / `MINOR` / `PASS` / `DEGRADED`（超时降级）/ `ERROR`（执行异常）

**`FuncResult`**：`func_id` / `func_name` / `clause_id` / `operator` / `threshold` / `actual` /
`result`（PASS/FAIL）/ `delta` / `severity` / `entity_id` / `entity_type` / `params` / `confidence`

**`AtomicFunction`**：`func_id` / `name` / `category` / `clause_id` / `description` / `operator` /
`threshold` / `unit` / `target_entities` / `depends_on` / `requires_global_context`；`DEFAULT_TIMEOUT = 30`

- `__post_init__`：归一化 `set → sorted list`（保证 `[0]` 索引与 `matches()` 稳定）；
  操作符归一化 `ge/le/eq/lt/exist/not_exist → >=/<=/==/</>=/<=`
- `matches(entity)`：`target_entities` 为空则匹配所有，否则按 `entity["type"]` 匹配
- `execute(entity=None)`：`entity=None` 为「缺失检查模式」——EXIST 类返回 FAIL，其他返回 None；
  EXIST 类特殊处理 `exists`/`count`/`_test_value` 属性并尊重 operator

### 3.2 `FuncRegistry`

- `timeout = 30`
- 从 `atomic` 子包导入 `ATOMIC_FUNCTIONS` 并 `_clone_atomic_function` 注册
- `resolve_dependencies()`：拓扑排序；`check_dependencies()`
- `execute_with_timeout(...)`（P94 直接同步执行，异常 → `Severity.ERROR`）
- `execute_batch(...)` / `execute_missing_batch(...)`

### 3.3 原子函数分片 — `src/baa_engine/atomic/`

`__init__.py` 通过 `_merge_modules` 按 `func_id` 去重合并：

| 分片 | 主题 | 数量 |
| --- | --- | --- |
| `fire_general/`（`dim_functions` / `exist_functions` / `count_functions` / `distance_functions` / `area_functions` / `attr_functions` / `light_functions` / `evac_functions`） | 通用消防 + 车库 | 81 / 75 / 17 / 19 / 19 / 16 / 10 / 4 |
| `fire_sprinkler.py` | GB50974 喷淋 | 68 |
| `fire_alarm.py` | GB50116 火灾报警 | 57 |
| `accessibility.py` | GB50763 无障碍 | 33 |
| `thermal.py` | 热工节能 | 16 |
| `structural.py` | 结构荷载 | 16 |

> 合计 **431** 条原子函数（按 `AtomicFunction()` 定义计数）。

---

## 4. 规范知识库 — `src/baa_engine/spec_data/`

### 4.1 `Clause` / `Threshold` / `SpecRepository` — `_repo.py`

- `Threshold`：`value` / `unit` / `operator` / `building_types`
- `Clause`：`clause_id` / `standard` / `title` / `text` / `level`(L1-L3) / `func_id` / `category` / `params` / `threshold`
- `SpecRepository`：
  - 内存索引 `_clauses`，key = `"{standard}:{clause_id}"`
  - 加载 `INITIAL_CLAUSES` + `NFPA_CLAUSES` + `GB50016_CLAUSES` + `GB50974_CLAUSES` + `GB50763_CLAUSES` + `GB50067_CLAUSES`
  - `get` / `get_by_func` / `list_all` / `list_by_level` / `list_by_category`
  - `get_threshold(func_id, building_type)`：支持按建筑类型覆盖阈值，缺省返回 `(0.0, "", ">=")`
  - `to_json` / `save_json` / `set_threshold`（供反馈学习写入）/ `list_standards` / `count`

### 4.2 条款数据分片

| 文件 | 标准 | 条款数 |
| --- | --- | --- |
| `gb50016_core.py`（`INITIAL_CLAUSES`） | GB50016 核心 | 31 |
| `gb50016_extra.py`（`GB50016_CLAUSES`） | GB50016 扩展 | 58 |
| `gb50974.py` | 消防给水及消火栓 | 54 |
| `gb50763.py` | 无障碍设计 | 29 |
| `gb50067.py` | 汽车库/修车库/停车场 | 16 |
| `nfpa.py` | NFPA101 / NFPA5000 | 11 |

> 合计 **199** 条 `Clause`。

### 4.3 版本管理 — `versioning.py`

`SpecVersion`、`ClauseChange`、`VersionManager`；支持版本 `GB50016` / `GB50974` / `GB50763` / `GB50067` / `NFPA101` / `NFPA5000`。

### 4.4 施工图审查 — `construction_review.py`

`ConstructionReviewItem`、`get_construction_review_items(...)`（支持按 `major` / `level` / `category` / `check_method` 过滤）。

### 4.5 兼容层 — `src/baa_engine/spec_repository.py`

薄转发层，从 `spec_data._repo` 转发 `Clause` / `SpecRepository` / `Threshold` 及全部条款列表，保证旧 import 路径可用。

---

## 5. 归因与修正

| 组件 | 位置 | 关键接口 |
| --- | --- | --- |
| `AttributionAnalyzer` | `attribution_analyzer.py` | `Finding`（L11）、`build_finding`（L23） |
| `CorrectionEngine` | `correction_engine.py` | `CorrectionAction`（L24：resize/add/replace/relocate/seal/upgrade/enlarge/add_lighting）、`CorrectionSuggestion`（L38）、`CorrectionEngine`（L763：`generate`、`_clause_to_func`） |
| `LLMCorrectionEngine` | `llm_correction.py` | `CorrectionSuggestion`（L38）、`LLMCorrectionEngine`（L55）：模式 `rule`/`llm`/`hybrid`；env `BAA_CORRECTION_MODE` / `BAA_LLM_ENDPOINT` / `BAA_LLM_API_KEY` / `BAA_LLM_MODEL`；`_extract_spatial_context` |

---

## 6. 报告生成 — `src/baa_engine/report_generator/`

| 文件 | 关键内容 |
| --- | --- |
| `main.py` | `ReviewReport`：`generate` → `build_cover` / `PageBreak` / `build_score_page` / `build_summary_page` / `build_structured_summary_page` / `build_diff_page` / `build_violation_pages` / `build_correction_pages` / `build_doc` |
| `components.py` | `ColorBar`(L99)、`StatCard`(L115)、`ensure_font`(L45)、`build_styles`(L148)、`make_table`(L256)、`build_doc`(L294)；字体采用 TrueType 优先 + 逐候选 try/except（兼容 macOS CFF 字体） |
| `cover.py` | 封面页 |
| `score.py` | `_build_category_bar`、`build_score_page`；评分 / 通过率 / 严重级别分布 |
| `summary.py` | `build_summary_page`、`build_structured_summary_page` |
| `violations.py` | `build_violation_pages`(L17)、`build_correction_pages`(L129) |
| `diff.py` | 差异对比页 |
| `correction_notice.py` | 修正通知书 |

---

## 7. 反向重构 — `src/baa_engine/reverse_engine.py`

- `RoomType`(L21)、`RoomSpec`(L34)、`LayoutConstraint`(L44)
- `ReverseEngine`(L57)：`infer_constraints` / `generate_dxf` / `export_dwg`（`_export_via_libreoffice`，env `BAA_SOFFICE_PATH`）
- `RoomPlacement`(L422)、`MultiRoomLayout`(L435)、`MultiRoomEngine`(L444)：`generate_layout` / `build_dxf`

---

## 8. 运行时基础设施

### 8.1 `ReviewQueue` — `src/baa_engine/task_queue.py`

- `ReviewTask`：`task_id` / `file_id` / `status`（`queued`|`running`|`completed`|`failed`）/ 时间戳 /
  `queue_position` / `progress` / `result` / `error` / `webhook_url` / `webhook_type`
- `ReviewQueue(max_concurrent=4, queue_timeout=300.0)`：
  `enqueue` / `dequeue` / `wait_and_dequeue` / `cancel` / `get_status` / `update_progress` /
  `complete` / `fail` / `_release_slot` / `run_consumer` / `cleanup` / `list_active` / `stats`；
  完成时触发 webhook。

### 8.2 `PersistentCache` — `src/baa_engine/cache.py`

`PersistentCache`(L44)：SQLite（WAL 模式），`get` / `set`（TTL + LRU），
`make_cache_key(...)`、单例 `get_cache()`。

### 8.3 `ApiKeyManager` — `src/baa_engine/api_key_manager.py`

`ApiKeyPermission`(L118)、`ApiKeyManager`(L159)：`baa_` 前缀原始密钥、SHA-256 哈希存储、
AES-GCM 加密元数据、过期控制、权限、用量统计。

### 8.4 反馈与学习 — `src/baa_engine/feedback_engine.py`

- `FeedbackRecord`(L21)、`FeedbackManager`(L89)：`submit` / `review` / `list` / `stats`（存储 `feedbacks.json`）
- `LearningEngine`(L230)：基于反馈生成阈值调整建议并写入 spec repo

### 8.5 团队协作 — `src/baa_engine/team_collab/`

- `models.py`：枚举 `UserRole` / `TeamRole` / `ProjectPermission` / `CommentType` / `ApprovalStatus` / `ReviewStatus`；
  ORM `User`(L103) / `Team`(L155) / `TeamMember`(L187) / `Project`(L214) / `ProjectMember`(L259) /
  `ReviewSession`(L285) / `ReviewComment`(L330) / `ApprovalFlow`(L369) / `ApprovalStep`(L409)
- `manager.py`：`CollaborationManager`(L90)（单例 SQLite、ORM session、token 生成/验证）

### 8.6 违规审核工作流 — `src/baa_engine/collab/audit.py`

`create_items_from_review` / `get_items` / `confirm_item` / `dismiss_item` / `pending_item` /
`update_note` / `get_stats` / `get_confirmed_items`；确认/驳回会回流 `FeedbackManager`。

### 8.7 其他

- `project_summary.py`：`aggregate_project_summary`(L40) / `_classify_overall_severity`(L212) / `format_project_report`(L235)
- `review_diff.py`：`DiffItem`(L16) / `DiffReport`(L35) / `ReviewDiffEngine`(L56)
- `yolo_integrator.py`：`YOLODetectionIntegrator`(L64)：`load_model` / `render_and_predict` / `detections_to_entities`（device cpu/xpu）
- `webhooks.py`：`build_webhook_payload`(L16) / `trigger_webhook`(L150)
- `i18n.py`：`t(key, lang, **kwargs)`(L295) / `supported_languages`(L325) / `is_supported`(L333)
- `model_params/exporter.py`：`get_function_params` / `get_layer_rules` / `get_construction_review_params` /
  `get_review_samples` / `get_spatial_graph` / `to_sft_jsonl` / `to_hf_dataset_description`

---

## 9. 接入层核心类

### 9.1 `BAAClient` — `src/sdk/__init__.py`

`BAAClient(api_key, base_url="http://localhost:8000", timeout=300.0)`。

- **HTTP 层**：`_headers` / `_url` / `_request`（httpx 优先，`_request_urllib` 兜底）/ `_get` / `_post`
- **核心方法**：`health` / `review` / `review_from_data` / `deconstruct` / `batch_review` / `reconstruct`
- **API v1**：`list_functions` / `list_specs` / `update_function` / `reverse_generate` / `reverse_generate_multi` /
  `correction_suggestions` / `review_history` / `review_detail` / `clear_review_history` / `review_project_summary` /
  `review_queue_status` / `cancel_review_task` / `thermal_k_value` / `render_drawing` / `list_construction_review_items` /
  `construction_review_report` / `export_review` / `review_multi_sheet` / `stats` / webhook CRUD /
  `submit_feedback` / `list_feedbacks` / `feedback_stats` / `review_feedback` / `adjust_threshold` /
  `model_params_*` / `export_model_params` / `create_task` / `collab_register` / `collab_login` / `collab_create_team`
- 异常：`BAAError`

### 9.2 `BAAMCPServer` — `src/mcp/baa_mcp_server.py`

`Server("baa-blueprint")`；MCP 工具：`baa_deconstruct` / `baa_review` / `baa_reconstruct`（付费，需 `auth_token`）/
`baa_health` / `baa_list_functions`（支持 `category` 过滤）/ `baa_review_from_data`；懒加载引擎 + `ThreadPoolExecutor(2)`。

### 9.3 服务入口 — `src/api/baa_api.py`

- FastAPI `app`（`title="BAA API"`，`version="1.25.0"`）
- `_load_engine_sync`：预热引擎单例；`_periodic_gc`（300s）；`_engine_thread` + lifespan join(timeout=120)
- `_sanitize_for_json`：递归清理 numpy 类型
- `generate_auth_token` / `verify_auth_token` / `_verify_with_secret`：JWT（HMAC-SHA256，`AUTH_SECRETS` 宽限期）
- 路由挂载：`collab_router`、`admin_router`、`review_router`、`render_router`、
  `case_router`（`/api/v1`）、`model_params_router`（`/api/v1`）、`audit_router`

### 9.4 全局单例 — `src/api/api_globals.py`

`PROJECT_ROOT` / `DATA_DIR` / `FILES_DIR` / `MODELS_DIR`；`SUPPORTED_FORMATS = {"dxf","dwg"}`；
`MAX_FILE_SIZE_MB = 50`；`API_KEYS` / `AUTH_SECRETS`；`ENGINE_THREAD_POOL`；
`_tasks` / `_webhooks` / `_persistent_cache` / `_review_cache`（`_REVIEW_CACHE_MAX=100`）；
`get_key_manager` / `generate_file_id` / `store_file` / `get_file_path` / `extract_api_key` /
`verify_api_key` / `require_admin`；`MAX_CONCURRENT_REVIEWS=4`、`_review_queue = ReviewQueue(4, 300.0)`。
