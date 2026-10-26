# D2-T3 离线导出方案

> **来源**：`docs/roadmap-phase-d-execution-plan.md` 第 2 节 T-D2  
> **Roadmap 验收**：用户可下载完整交付包，断网可查看  
> **写作日期**：2026-10-26  
> **前置**：T-C4（PDF/IFC/STEP 导出已交付）、T-C6（SDK wheel 已交付）  
> **本方案范围**：D2-T3（`POST /exports/{review_id}` 产出 zip + manifest.json + SDK `export_bundle`），不含 D2-T4/D2-T5  

---

## 1. 现状分析

### 1.1 代码库现状
- **导出能力**：`step_export.py` / `ifc_export.py` 已交付 DXF→IFC/STEP 转换；PDF 报告由 T-C5 生成器产出。
- **审查引擎**：`review_routes.py` 提供 `GET /reviews/{id}` 及 `GET /reviews/{id}/report`（PDF）。
- **SDK**：`src/sdk/` 已有 `KnowledgeBundle` + `export_bundle` 预留接口（T-C6）。
- **无 zip 打包端点**：目前无 `POST /exports/{review_id}` 或类似批量下载接口。
- **manifest.json**：无定义，需新建 schema。

### 1.2 现有导出接口盘点
| 接口 | 方法 | 产出 | 状态 |
|------|------|------|------|
| `/reviews/{id}/report` | GET | PDF 报告 | ✅ 已交付 |
| `/reviews/{id}/export/ifc` | GET | IFC 文件 | ✅ 已交付 |
| `/reviews/{id}/export/step` | GET | STEP 文件 | ✅ 已交付 |
| `/reviews/{id}/dxf` | GET | DXF 源文件副本 | ✅ 已交付 |
| `/exports/{review_id}` | POST | zip 全包 | ❌ 待实现 |

---

## 2. 改造目标与验收标准

### 2.1 Roadmap DoD（原文）
- [ ] `POST /exports/{review_id}` 产出 zip（含 DXF 源文件副本 + PDF 报告 + IFC/STEP 导出 + 标准集版本标记 manifest.json）。
- [ ] 依赖：T-C4（PDF/IFC/STEP 均已交付导出接口）。
- [ ] manifest.json 字段：`review_id` / `exported_at` / `standard_set` / `ifc_path` / `step_path` / `dxf_sha256` / `report_version`。
- [ ] SDK 新增 `export_bundle(review_id)` 方法（wheel 更新）。

### 2.2 本方案验收标准
| 验收项 | 标准 |
|--------|------|
| 端点可用 | `POST /exports/{review_id}` 返回 200 + zip 下载 URL |
| zip 内容 | 含 DXF + PDF + IFC + STEP + manifest.json，共 5 个文件 |
| manifest 完整 | 7 个字段全部非空，`dxf_sha256` 与 DXF 文件 hash 一致 |
| 断网可查看 | 解压 zip 后，PDF 可打开，IFC/STEP 可被 CAD 软件读取 |
| SDK 方法 | `sdk.export_bundle(review_id)` 返回本地 zip 路径 |
| 性能 | 单个审查导出 < 30s（含 IFC/STEP 转换） |
| 并发 | 同一 review_id 并发请求返回同一 zip（幂等） |

---

## 3. 改造范围（分阶段）

### 3.1 阶段 A：后端 zip 打包服务（1 天）

**目标**：实现 `POST /exports/{review_id}` 端点，产出 zip 并返回下载 URL。

**改动**：

#### 后端路由（`src/api/exports/`）
1. 新建 `src/api/exports/export_routes.py`：
   - `POST /exports/{review_id}`：触发打包，返回 `{download_url, manifest}`。
   - `GET /exports/{review_id}/download`：下载 zip 文件。
2. 路由注册到 `baa_api.py`。

#### 服务层（`src/baa_engine/export_bundle.py`）
1. `ExportBundleService` 类：
   - `build(review_id) -> Path`：收集 DXF/PDF/IFC/STEP → 打包 zip → 返回路径。
   - `get_or_create(review_id) -> Path`：幂等，已有 zip 直接返回。
   - `_collect_files(review_id) -> list[Path]`：从各导出接口收集文件。
   - `_compute_manifest(review_id, files) -> dict`：生成 manifest.json。
   - `_zip_files(files, manifest, output_path) -> Path`：zip 打包。

#### manifest.json schema
```json
{
  "review_id": "uuid",
  "exported_at": "2026-10-26T12:00:00Z",
  "standard_set": "CN-National-v1",
  "ifc_path": "review_abc.ifc",
  "step_path": "review_abc.step",
  "dxf_sha256": "a1b2c3...",
  "report_version": "v2.5.80",
  "report_schema_version": "1.0"
}
```

#### 文件收集策略
- DXF：从 `src/data/reviews/{review_id}/source.dxf` 读取（或调 `/reviews/{id}/dxf`）。
- PDF：从报告生成器缓存读取（或调 `/reviews/{id}/report`）。
- IFC/STEP：调用 `ifc_export` / `step_export` 模块直接转换（避免 HTTP 自调用）。
- zip 存储路径：`src/data/exports/{review_id}.zip`（或配置 `EXPORT_DIR`）。

**产出**：
- `src/api/exports/export_routes.py`
- `src/baa_engine/export_bundle.py`
- 路由注册

**风险**：中（IFC/STEP 转换耗时，需异步或超时控制）

### 3.2 阶段 B：SDK `export_bundle` 方法（0.5 天）

**目标**：SDK 新增 `export_bundle(review_id)` 方法， wheel 更新。

**改动**：
1. `src/sdk/baa_sdk/export.py`（或 `client.py`）新增：
   ```python
   def export_bundle(self, review_id: str, output_dir: str = ".") -> Path:
       """下载审查交付包 zip 到本地。"""
   ```
2. 方法内部：调 `POST /exports/{review_id}` → 获取 `download_url` → 下载 zip → 保存到 `output_dir` → 返回 `Path`。
3. SDK 版本号 bump（如 `2.5.80 → 2.5.81`）。
4. wheel 重新打包。

**产出**：
- SDK 方法 + 单测
- wheel 更新

**风险**：低（SDK 已有 HTTP 客户端，只需新增方法）

### 3.3 阶段 C：幂等 + 缓存 + 性能优化（0.5 天）

**目标**：同一 review_id 并发请求返回同一 zip；大文件异步处理。

**改动**：
1. **幂等**：`get_or_create` 检查 `src/data/exports/{review_id}.zip` 是否存在，存在直接返回。
2. **锁**：使用文件锁（`filelock` 或 `fcntl`）防止并发打包。
3. **异步**（可选）：如果 IFC/STEP 转换 > 10s，返回 `202 Accepted` + 轮询 `GET /exports/{review_id}/status`。
4. **清理**：可配置 `EXPORT_RETENTION_DAYS`（默认 7 天），过期 zip 自动删除。

**产出**：
- 幂等逻辑 + 锁
- 可选异步 + 状态查询

**风险**：低

### 3.4 阶段 D：验收测试（0.5 天）

**目标**：端到端验证 zip 内容、manifest 完整性、SDK 方法。

**改动**：
1. `src/tests/test_export_bundle.py`：
   - `test_export_endpoint_returns_zip`：POST 返回 200 + download_url。
   - `test_zip_contains_required_files`：解压后含 DXF/PDF/IFC/STEP/manifest.json。
   - `test_manifest_fields`：7 个字段非空，dxf_sha256 一致。
   - `test_idempotent`：并发请求返回同一 zip。
   - `test_sdk_export_bundle`：SDK 方法下载到本地。
2. 手动验证：解压 zip → PDF 可打开 → IFC 可被 FreeCAD 读取。

**产出**：
- 5 个测试用例
- 手动验收 checklist

---

## 4. 技术选型

| 选型 | 决策 | 理由 |
|------|------|------|
| zip 打包 | Python `zipfile` | 标准库，无额外依赖 |
| 文件锁 | `filelock`（pip）或 `fcntl`（Unix） | 跨平台，防止并发打包 |
| 异步任务 | 可选 Celery / 后台线程 | MVP 先同步，超时 30s |
| 存储路径 | `src/data/exports/` | 与现有 `src/data/` 一致 |
| SDK 下载 | `requests` / `urllib` | SDK 已有 HTTP 客户端 |

---

## 5. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| IFC/STEP 转换耗时 > 30s | 中 | 异步处理 + 轮询状态；或预生成缓存 |
| 磁盘空间不足（zip 堆积） | 低 | 配置保留天数 + 定时清理 |
| 并发打包 race condition | 中 | 文件锁 + 幂等检查 |
| SDK 版本不兼容 | 低 | `report_schema_version` 字段 + `VersionMismatchError` |
| DXF 文件缺失 | 中 | 端点返回 404 + 明确错误信息 |

---

## 6. 执行计划

### 6.1 阶段 A：后端 zip 打包服务（1 天）
- [ ] 新建 `src/api/exports/export_routes.py`
- [ ] 新建 `src/baa_engine/export_bundle.py`
- [ ] 路由注册到 `baa_api.py`
- [ ] `POST /exports/{review_id}` + `GET /exports/{review_id}/download`
- [ ] manifest.json 生成 + zip 打包
- [ ] 跑全量回归验证

### 6.2 阶段 B：SDK 方法（0.5 天）
- [ ] SDK `export_bundle(review_id)` 方法
- [ ] 单测
- [ ] wheel bump + 重新打包

### 6.3 阶段 C：幂等 + 缓存（0.5 天）
- [ ] `get_or_create` 幂等逻辑
- [ ] 文件锁
- [ ] 可选异步 + 状态查询
- [ ] 清理策略

### 6.4 阶段 D：验收测试（0.5 天）
- [ ] `test_export_bundle.py`（5 个用例）
- [ ] 手动验证 zip 内容
- [ ] commit

**总计**：2.5 天

---

## 7. 依赖与前置

- **T-C4 IFC/STEP 导出**：已交付（`ifc_export.py` / `step_export.py`）
- **T-C5 PDF 报告**：已交付（报告生成器稳定）
- **T-C6 SDK**：已交付（wheel + `KnowledgeBundle`）
- **D1-T1 标准集**：已交付（标准集元数据注入 manifest）

---

## 8. 后续任务

- **D2-T4 图纸可视化移动端优化**：双指缩放 + 点击定位
- **D2-T5 小程序发布**：企业微信应用创建 + 提审 + 发布
- **D2-T6 多端指标看板**：移动端可用 + 离线导出可用的数据支撑

---

## 9. 附录

### 9.1 关键文件路径（新建/修改）
- `src/api/exports/export_routes.py`（新建）
- `src/baa_engine/export_bundle.py`（新建）
- `src/sdk/baa_sdk/export.py`（修改：新增 `export_bundle`）
- `src/tests/test_export_bundle.py`（新建）
- `src/data/exports/`（新建目录，zip 存储）

### 9.2 manifest.json 字段定义
| 字段 | 类型 | 说明 |
|------|------|------|
| `review_id` | string | 审查任务 ID |
| `exported_at` | string (ISO 8601) | 导出时间戳 |
| `standard_set` | string | 标准集 code（如 `CN-National-v1`） |
| `ifc_path` | string | zip 内 IFC 文件名 |
| `step_path` | string | zip 内 STEP 文件名 |
| `dxf_sha256` | string | DXF 文件 SHA-256 hash |
| `report_version` | string | 报告版本号 |
| `report_schema_version` | string | 报告 schema 版本（D3-T4 预留） |

### 9.3 zip 内容清单
```
review_{id}.zip
├── source.dxf          # DXF 源文件副本
├── report.pdf          # PDF 报告
├── model.ifc           # IFC 导出
├── model.step          # STEP 导出
└── manifest.json       # 元数据
```