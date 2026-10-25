# T-C2 并发与扩展 — 验收证据链

日期：2026-10-21　分支：main　迁移版本：`0002`（在 T-C1 `0001` 之上）

## 1. 目标与范围

Roadmap 阶段 C 的 T-C2「并发与扩展」：分布式限流 + 服务无状态化 + HPA 配置。

验收标准（roadmap）：

- 水平扩容 2→N 生效（吞吐随副本数上升）。
- 限流在多副本下一致生效（非单进程内存态）。

本机无 k8s 集群，按确认口径以**多进程 + 共享 PostgreSQL**模拟多副本（同 Pod/副本语义：
独立进程、独立内存、共享存储）。

## 2. 实现设计

### 2.1 分布式限流（`src/baa_engine/rate_limit.py`）

| 项 | 说明 |
|---|---|
| 算法 | 固定窗口计数，桶键 `{subject}:{window_start}` |
| 存储 | 统一库 `rate_limit_buckets`（PG/SQLite 同一份实现） |
| PG 原子性 | `INSERT ... ON CONFLICT DO UPDATE ... WHERE count < limit RETURNING count`，单语句完成「判定 + 计数」 |
| SQLite 原子性 | `INSERT ... ON CONFLICT DO NOTHING` + 条件 `UPDATE ... WHERE count < limit`（写锁串行化） |
| 过期清理 | 每 200 次调用惰性 `DELETE expires_at < now`，无后台常驻任务 |
| 可用性 | 存储异常 fail-open（放行 + 告警），不阻断业务 |
| 接入点 | `verify_api_key` → `_enforce_rate_limit`（按密钥权限取 `DEFAULT_RATE_LIMIT`）；环境变量 admin 通道（`__env__`）不限流 |
| 开关 | `BAA_RATE_LIMIT_ENABLED=0` 可整体关闭 |

改造前该能力是**死代码**：`check_rate_limit` 无调用点，判定用进程内 dict + 本地 JSON，
多副本下各算各的。

### 2.2 服务无状态化（核心三件）

| 域 | 存储 | 跨副本语义 |
|---|---|---|
| 限流计数 | `rate_limit_buckets` | 同一配额全副本共享，原子不超发 |
| API 密钥/用量 | `api_keys` / `api_key_usage` | 密钥增删改 ≤5s（`BAA_API_KEY_CACHE_TTL`）可见；用量原子 UPSERT 累计 |
| 审查任务队列 | `review_tasks` | 任一副本入队、任一工作副本原子认领；状态/进度/结果全局可查 |

关键取舍：

- **不覆盖副本间数据**：密钥 `save()` 只 upsert 本进程已知 key 并仅删除本进程显式 delete 的
  `key_id`（`_deleted` 集合）；用量**只补建缺失行**，绝不写回本地快照（否则陈旧副本会把
  其他副本已累计的计数回退，lost update）。
- **任务认领**：PG 用 `SELECT ... FOR UPDATE SKIP LOCKED` + 条件 `UPDATE ... WHERE status='queued'`；
  SQLite 用条件 UPDATE（写锁串行化）。`rowcount != 1` 即视为被其他副本抢走，重试下一轮。
- **并发闸门按副本**：`running_count` 保持进程本地（每 Pod `max_concurrent`），任务状态全局。
- **命名空间**：`BAA_QUEUE_NAMESPACE`（生产 `default`），测试用独立 namespace 避免行级干扰。
- **降级路径**：统一库不可用时队列/限流退回进程内实现并告警，保证服务可用。
- **显式隔离语义**（沿用 T-C1）：`ApiKeyManager(storage_path=显式)` 与显式 URL 的
  `CollaborationManager` 仍走独立 JSON/库，仅默认路径接统一库。

### 2.3 HPA / 部署配置

改造前 HPA 已配 min2→max10，但 Deployment `replicas: 3` + PVC `ReadWriteOnce` 导致多副本
挂载失败，扩容实际跑不起来。

本次修正（`k8s/baa-deployment.yaml`）：

- `baa-data-pvc` `ReadWriteOnce` → `ReadWriteMany`（图纸跨副本可读；仅块存储时改用对象存储，注释已说明）
- 新增 PostgreSQL `StatefulSet` + headless `Service` + `pg-data` 模板（`postgres:17-alpine`，探针 `pg_isready`）
- Secret 增加 `BAA_DATABASE_URL` / `POSTGRES_*`；ConfigMap 增加 `BAA_RATE_LIMIT_ENABLED` / `BAA_QUEUE_NAMESPACE`
- 新增 `PodDisruptionBudget`（`minAvailable: 1`）；HPA 配置保留（CPU 70% / 内存 80%）

`docker-compose.yml`：新增 `postgres` 服务（healthcheck + `depends_on`），`baa` 注入
`BAA_DATABASE_URL` / `BAA_RATE_LIMIT_ENABLED` / `BAA_QUEUE_NAMESPACE`；去掉 `container_name`
以支持 `--scale baa=N`（多副本需移走固定 host 端口，由反向代理转发）。

### 2.4 Alembic 0002

`alembic/versions/0002_tc2_stateless.py`：新增 `rate_limit_buckets` / `api_keys` /
`api_key_usage`（FK CASCADE）/ `review_tasks`（2 索引）；downgrade 全逆序可重建。

存量密钥搬迁：`migration_tool.migrate_api_keys()` + CLI `--api-keys`（**显式执行**，
不并入默认全量搬迁，避免测试/演示库误吃到生产密钥；按 key_id 幂等插入）。

## 3. 验收结果

### 3.1 多进程验收（`src/tests/test_pg_cluster.py`，`pytest -m pg`）

| # | 验收项 | 场景 | 结果 |
|---|---|---|---|
| 1 | 限流跨副本一致 | 4 个独立进程各抢同一 `limit=5` 配额（各 8 次尝试，共 32 次） | 总放行**恰为 5**，无超发无漏发 ✅ |
| 2 | 任务跨副本互见 + 原子认领 | 父进程入队 8 个任务，3 个工作进程并发认领 | 8 个任务**各被认领一次**、全部 `completed`、`worker_id` 覆盖 ≥2 个副本 ✅ |
| 3 | 密钥/用量跨副本可见 | 进程 A 建密钥 → 进程 B 验证并 `record_usage` ×3 → 进程 C 读统计 | 验证通过、`total_calls=3`、`last_used` 有值 ✅ |
| 4 | 吞吐随副本数上升 | 同一任务集 40 个 × 50ms：1 副本 vs 2 副本 | 2 副本耗时 < 1 副本 × 0.8（断言通过） ✅ |

### 3.2 单测

| 文件 | 用例 | 覆盖 |
|---|---|---|
| `test_rate_limit.py` | 7 | 精确边界 / 主体隔离 / 窗口滚动 / limit≤0 / reset / 开关 / 同库双实例共享 |
| `test_api_key_db.py` | 5 | 密钥跨实例可见 / 用量累计 / 删除可见 / 陈旧副本不回退用量 / JSON 备份保留 |
| `test_task_queue_db.py` | 5 | 跨副本认领 / 原子单次认领 / 进度与完成互见 / 取消互见并跳过 / 全局统计 |
| `test_task_queue.py` | 17 | 原有内存行为 16 用例全部保留 + 逐用例清表 fixture |

### 3.3 迁移与回归

- Alembic 0002：`upgrade head` ×2 幂等；`downgrade 0001` → `upgrade head` 回路通过（SQLite 实测）。
- PG 全量验收模块（T-C1 4 项 + T-C2 4 项）：`8 passed`（见 `pg_cluster.txt`）。
- 全量回归：
  - 无 PG 环境：`2537 passed / 0 failed / 22 skipped`（22 skip 含 PG 验收模块）
  - 带 `BAA_TEST_PG_URL`：`2545 passed / 0 failed / 14 skipped`（见 `regression.txt`）

## 4. 过程缺陷与修复

| 缺陷 | 根因 | 修复 |
|---|---|---|
| 密钥单测 `assert 9 == 2` | DB 化后显式 `storage_path` 隔离失效，历史测试密钥残留在共享库 | `_use_db = storage_path is None`：显式路径继续 JSON 隔离（镜像 T-C1 显式 URL 语义） |
| 多副本 `save()` 回退用量 | 写本地用量快照覆盖库中已累计值（lost update） | 用量改为**只补建缺失行**，计数仅由原子 UPSERT 推进 |
| 多副本首启 `DuplicateTable` | 各副本同时 `ensure_schema` 竞争建表 | 建表失败后校验表是否齐全，齐全视为成功（其他副本已建） |
| PG 验收脏状态 `DuplicateTable` / 净增 0 | 前次模块用 `ensure_schema` 建表但 `alembic_version` 无记录，`downgrade base` 空转 | `_reset_to_base` 检测「版本表存在但无记录」时 `drop_all` 清场（仅测试代码） |
| `test_pg_acceptance` / `test_migrations` 版本断言 0001 | 新增 0002 迁移 | 断言更新为 `0002` 并校验 4 张新表 |

## 5. 已知限制

- 任务发现延迟：跨副本新任务最长约 `_POLL_INTERVAL`（200ms）被发现；同副本入队即时唤醒。
- `running_count` 为副本本地视角；`queued/completed/failed` 为命名空间全局。
- 密钥 JSON 备份仍写共享 `/app/data/api_keys.json`，多副本下内容以最后写入者为准；
  **权威数据在统一库**，JSON 仅供旧工具/人工排障，不作为读取来源。
- PVC `ReadWriteMany` 依赖集群具备 RWX 存储类（NFS/CephFS/EFS）；仅块存储场景需改用对象存储承载图纸。
- PG 的 `SKIP LOCKED` 保证认领不重复；SQLite 依赖写锁串行化（单机多进程可用，非生产目标）。
