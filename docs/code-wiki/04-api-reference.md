# 04 · REST API 参考

FastAPI 应用入口：`src/api/baa_api.py`（`app.title = "BAA API"`，`version = "1.25.0"`）。
启用 Swagger UI（`/docs`）、ReDoc（`/redoc`）与 OpenAPI（`/openapi.json`）。

## 鉴权模型

| 方式 | 说明 |
| --- | --- |
| API Key（`Authorization: Bearer <key>`） | `verify_api_key` 校验；`API_KEYS` 为空时允许匿名 |
| JWT `auth_token`（HMAC-SHA256） | `generate_auth_token` / `verify_auth_token`，支持 `AUTH_SECRETS` 宽限期 |
| 管理员 | `require_admin` 校验 |

---

## 1. 核心端点（`baa_api.py` 直接定义）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/` | 服务根信息 |
| GET | `/health` | 健康检查（子系统状态 + YOLO + psutil 内存） |
| POST | `/deconstruct` | 图纸解构为结构化实体（解析 → 语义 → 可选 YOLO → 尺寸注入 → 规范判定） |
| GET | `/api/v1/functions` | 列出全部原子函数 |
| GET | `/api/v1/specs` | 列出规范标准 |
| GET | `/api/v1/specs/versions` | 规范版本列表 |
| GET | `/api/v1/specs/compare` | 版本对比 |
| GET | `/api/v1/specs/change-log` | 条款变更日志 |
| POST | `/api/v1/functions/{func_id}/update` | 更新原子函数参数 |
| POST | `/api/v1/reverse` | 反向重构单房间 |
| POST | `/api/v1/reverse/multi` | 反向重构多房间布局 |
| POST | `/api/v1/reverse/export-dwg` | 反向重构导出 DWG |
| POST | `/api/v1/correction/suggestions` | 修正建议 |
| GET/POST | `/api/v1/construction-review[/report]` | 施工图审查项与报告 |
| GET | `/api/v1/stats` | 审查统计仪表盘 |

### `/deconstruct` 流程
格式/大小校验 → `store_file` → 线程池 `parse` → `SemanticAnalyzer.analyze` →
可选 YOLO 增强 → `DimensionParser` 注入 → `_do_deconstruct_step3`（规范判定 + 缺失检查 + 统计）。

---

## 2. 审查链路 · `src/api/review/`

路由前缀为空（`router = APIRouter(tags=["Review","review"])`），路径即下表所列。

### 2.1 主链路 — `review_routes.py`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/review` | **核心审查**（多段上传图纸） |
| POST | `/review-from-data` | 从结构化实体直接审查（跳过解析） |
| GET | `/review/pdf` | 生成审查 PDF |
| GET | `/review/export` | 导出审查结果 |
| POST | `/thermal/k-value` | 热工 K 值反算 |
| POST | `/reconstruct` | 从结构化数据重建图纸 |
| GET | `/order/{order_id}` | 查询审查任务结果 |
| POST | `/review-multi-sheet` | 多 Sheet 图纸审查 |

**`/review` 内部链路**：格式与大小校验 → `store_file` → 内存缓存 `_get_rc()[cache_key]` +
持久化缓存 `_get_pc().get(cache_key, "review_result")`（cache_key = `make_cache_key(file_hash, standard, building_type)`）
→ `review_state`（`timeout_seconds` 10~600，`_check_timeout()` 返回 partial）→
`_get_rq().wait_and_dequeue`（队列超时 `QUEUE_TIMEOUT=300s`）→
Step1 解析（progress 10）→ `drawing_type`/`corrupt` 判定（非建筑图 → `status=skipped`；
损坏 → `CORRUPT_FILE`）→ Step2 语义分析（progress 50→70）→ Step3 规范判定。

### 2.2 渲染与队列 — `render_routes.py`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/review/queue/{task_id}` | 队列任务状态 |
| GET | `/review/queue/stats` | 队列统计 |
| GET | `/render/{file_id}` | 渲染图纸 |
| GET | `/render/{file_id}/overlay` | 渲染叠加层（违规标注） |
| GET | `/review/{file_id}/pdf` | 按 file_id 生成审查 PDF |
| GET | `/review/project/summary` | 项目级汇总 |

### 2.3 对比与批量 — `compare_routes.py` / `batch_routes.py`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/review/compare` | 两份审查结果对比 |
| POST | `/batch-review` | 批量审查（同步） |
| POST | `/batch-review-stream` | 批量审查（SSE 流式） |

### 2.4 历史 — `history_routes.py`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/review/history` | 审查历史列表 |
| DELETE | `/review/history/{review_id}` | 删除某条历史 |
| DELETE | `/review/queue/{task_id}` | 取消队列任务 |

### 2.5 案例库 — `case_routes.py`（前缀 `/api/v1`）

`GET /cases`、`GET /cases/search`、`GET /cases/stats`、`GET /cases/{case_id}`

---

## 3. 管理端点 — `src/api/admin_routes.py`

### 3.1 API 密钥

| 方法 | 路径 |
| --- | --- |
| POST/GET | `/admin/keys` |
| GET | `/admin/keys/stats` |
| GET | `/admin/keys/{key_id}` |
| POST | `/admin/keys/{key_id}/revoke` |
| POST | `/admin/keys/{key_id}/rotate` |
| DELETE | `/admin/keys/{key_id}` |
| POST | `/admin/keys/verify` |
| GET | `/admin/bootstrap-key` |

### 3.2 任务 / Webhook / 反馈

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST/GET | `/api/v1/tasks[/{task_id}[/result]]` | 异步任务创建与查询 |
| POST/GET/DELETE | `/api/v1/webhooks[/{webhook_id}]` | Webhook 管理 |
| POST/GET | `/api/v1/feedbacks` | 提交 / 列出反馈 |
| GET | `/api/v1/feedbacks/stats`、`/api/v1/feedbacks/{feedback_id}` | 反馈统计与详情 |
| POST | `/api/v1/feedbacks/{feedback_id}/adjust` | 阈值调整 |

---

## 4. 协作端点 — `src/api/collab_routes.py`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/collab/auth/register` | 注册 |
| POST | `/collab/auth/login` | 登录 |
| GET/PUT | `/collab/users/me` | 当前用户 |
| GET | `/collab/users/search` | 搜索用户 |
| POST/GET/GET{id} | `/collab/teams` | 团队 CRUD |
| POST/DELETE | `/collab/teams/{team_id}/members` | 团队成员 |
| POST/GET/GET{id} | `/collab/projects` | 项目 CRUD |
| POST/PUT/DELETE | `/collab/projects/{id}/members` | 项目成员 |
| GET | `/collab/teams/{team_id}/projects` | 团队项目 |
| POST | `/collab/review-sessions` | 创建评审会话 |
| GET | `/collab/projects/{id}/review-sessions` | 项目评审会话 |
| GET | `/collab/review-sessions/{id}` | 评审会话详情 |
| PUT | `/collab/review-sessions/{id}/status` | 更新状态 |
| POST/GET | `/collab/review-sessions/{id}/comments` | 评论 |
| PUT | `/collab/comments/{id}/resolve` | 解决评论 |
| POST/GET | `/collab/review-sessions/{id}/approval-flow` | 审批流 |
| POST | `/collab/approval-steps/{step_id}/approve` / `reject` | 审批操作 |
| GET | `/collab/stats` | 协作统计 |

---

## 5. 违规审核工作流 — `src/api/collab/audit_routes.py`（P119）

| 方法 | 路径 |
| --- | --- |
| GET | `/stats` |
| GET/POST | `/items` |
| POST | `/items/{item_id}/confirm`、`/dismiss`、`/pending` |
| GET | `/confirmed` |
| GET | `/export/pdf` |

---

## 6. 模型参数导出 — `src/api/model_params_routes.py`（前缀 `/api/v1`，P93）

`GET /model-params/functions`、`/layer-rules`、`/cd-items`、`/samples`、`/spatial-graph`、`/export`

---

## 7. 通用响应约定

- 成功：`{"status": "ok"|"success", "data": {...}}`（视端点而定）
- 失败：`{"status": "error", "message": "...", "error_code": "..."}`
- 上传约束：`SUPPORTED_FORMATS = {"dxf","dwg"}`（PDF 走专用管线），`MAX_FILE_SIZE_MB = 50`
- 并发：`MAX_CONCURRENT_REVIEWS = 4`，队列超时 300s

> SDK 侧对错误响应统一抛 `BAAError`。
