# T-C1 验收证据链：数据层升级 — 统一数据层与 PostgreSQL 迁移

> 日期：2026-10-20　分支：main　关联：roadmap 阶段 C T-C1（G14 / G17 / C1）

## 任务范围

抽象统一数据层（全项目唯一 engine/session 入口）→ PostgreSQL 多副本共享存储 +
Alembic 迁移脚本；历史 / 审计 / 缓存 / 协作四域全部接统一数据层；存量三 SQLite 库
搬迁工具 + 幂等保证；便携 PG 实测验收。

## 实施步骤与证据

### T1 统一数据层包 `src/baa_engine/db/`
- `database.py`：`resolve_database_url()`（显式参数 > `BAA_DATABASE_URL` > 默认
  `sqlite:///data/baa.db`）；`get_engine()` 惰性创建按 URL 缓存（`--preload` fork 安全：
  import 时不建任何连接）；SQLite 连接保留 WAL + `synchronous=NORMAL` PRAGMA，
  PG 启用 `pool_pre_ping`；`get_session_factory()`（scoped_session）；
  `ensure_schema()` 建表兜底（幂等）；`dispose_engine()` / `dispose_all()`
- `models/`：`base.py`（naming_convention 防 PG downgrade 断链）+
  `history.py`（ReviewHistory，JSON 列 + DateTime(timezone=True)）+
  `audit.py`（ReviewAuditItem）+ `cache.py`（CacheEntry，Float epoch 直拷）+
  `collab.py`（10 表 + 6 枚举 + 状态机白名单，自 team_collab/models.py 迁入）
- 兼容 shim：`team_collab/models.py` 全量 re-export（直接 import 仅 4 处，成本≈0）
- 单测：`test_db_url.py` 6 用例（URL 优先级 / 跨线程 / pool_pre_ping / 缓存与 dispose）

### T2 Alembic 接入
- `alembic.ini`（英文注释防 GBK）+ `env.py`（URL：`-x db_url=` > env > resolve；
  `render_as_batch=True`）+ `versions/0001_initial.py`（13 表全量，autogenerate）
- 验证（`test_migrations.py` 3 用例）：upgrade head ×2 幂等（二次无执行行）、
  downgrade base → upgrade head 重建 13 表、`alembic_version=0001`

### T3 协作域
- `team_collab/manager.py` 接统一 engine：默认路径走 `resolve_database_url()`，
  显式 db_path（测试隔离）保持独立 SQLite；`ensure_schema` 幂等兜底

### T4 历史域
- `api/review/review_history.py` 全量 session 化：5 个公开函数签名不变；
  JSON 列读出即对象（调用方 `json.loads/dumps` 全删）；`sf.remove()` 释放

### T5 审计域
- `baa_engine/collab/audit.py`：**删除模块级 `_init_db()` import 副作用**（改惰性
  ensure）；`_to_dict` 保持旧 sqlite3.Row 键名契约；`session.merge()` 等价
  INSERT OR REPLACE

### T6 缓存域
- `baa_engine/cache.py`：PersistentCache 单例保留；**`__init__` 不建 engine**
  （`api_globals.py` import 时即调 `get_cache()`，惰性化化解 fork 风险），
  首次使用经 `_sf()` 惰性建；全部读写 session 化；`close()` → `dispose_engine()`

### T7 搬迁工具 `db/migration_tool.py` + 单测
- 13 条搬迁计划（历史 2 表 / 缓存 1 表 / 协作 10 表）；只读 URI 连接源库
  （`mode=ro`，永不修改旧文件，回滚路径 = 新库异常回指旧文件）
- 幂等：SQLite `INSERT OR IGNORE` / PG `on_conflict_do_nothing(pk)`
- 类型转换：ISO / CURRENT_TIMESTAMP → DateTime；JSON 文本列 → JSON 列
  （双编码兜底原样存）；协作/缓存 Float epoch 零转换直拷
- 容错：源库缺表（旧库版本落后）标记 `error=1` 跳过不崩溃
- CLI：`python -m src.baa_engine.db.migration_tool --dry-run [--url ...]`
- 单测（`test_migration_tool.py` 5 用例）：迷你 legacy 三库 → 搬迁字段断言
  （JSON 读出即对象 / 时间戳转换 / Float 直拷）、二次搬迁 inserted=0、
  dry-run 零写入、源缺失 / 缺表报 error 不崩溃
- 测试隔离：`conftest.py` 在 import baa_api 前 `os.environ.setdefault` 指向
  per-pid 临时 SQLite，atexit 先 `dispose_all()` 再删文件

### T8 便携 PostgreSQL 验收（pytest -m pg）
- 环境：PostgreSQL 17.6 EDB Windows x64 binaries zip → `D:\tmp\pgsql`；
  `initdb -D D:\tmp\pgdata -U baa --auth=trust`；`pg_ctl -p 5433`；
  建库 `baa_test`；`BAA_TEST_PG_URL=postgresql+psycopg://baa@localhost:5433/baa_test`
- `pyproject.toml` 注册 `pg` marker；未设 `BAA_TEST_PG_URL` 时 4 用例全部 skip
  （默认回归不受影响）
- 四项验收（`test_pg_acceptance.py`）：
  1. upgrade ×2 幂等（13 表 + version 0001，重复验收先降 base 清场）
  2. 双进程并发三域读写（两个独立进程同时写历史/缓存/协作并回读，第三方连接互见
     —— PG 共享存储核心场景）
  3. downgrade base → upgrade head 重建
  4. 真实 legacy 三库搬迁行数比对（每表净增 == source 行数，二次搬迁 inserted=0）

## 验收结果

| 项目 | 结果 |
| --- | --- |
| T-C1 新增单测 | 15 passed（test_db_url 6 + test_migrations 3 + test_migration_tool 5 + 孤儿守卫 1） |
| pg marker skip（无环境） | 4 skipped（默认回归不受影响） |
| 全量回归（SQLite 基线） | **2520 passed / 0 failed / 18 skipped / 14 deselected**（基线 2505 + 15 新增） |
| T8 四项 PG 验收 | **4 passed**（upgrade×2 幂等 / 双进程并发三域读写 / downgrade 重建 / 真实搬迁行数比对） |

### T8 实跑记录

环境：PostgreSQL 17.6（EDB binaries zip → `D:\tmp\pgsql`，initdb -U baa --auth=trust，
端口 5433，库 baa_test）。详见 [pg_acceptance.txt](pg_acceptance.txt)。

搬迁行数比对（真实 legacy 三库 → PG，合计 source=1138 / target_total=732，二次搬迁 inserted 全 0）：

- review_history 634→634、cache_entries 2→2、协作域 10 表 96→96（users 30、teams 11、
  team_members 15、projects 8、project_members 8、review_sessions 7、
  rectification_records 2、review_comments 5、approval_flows 5、approval_steps 5）
- review_audit_items：406 行**全部为孤儿**（136 个 distinct review_id 均不在
  review_history，`test-*`/`e2e_*` 前缀 = 历史 E2E 与单测残留，旧 SQLite 库不强制
  外键所致）——按 FK 守卫设计跳过并计入 skipped，保证新库引用完整性（非搬迁缺陷）

## 改动清单

- 新增：`src/baa_engine/db/`（database.py、models/{base,history,audit,cache,collab}.py、
  migration_tool.py、__init__.py）、`alembic/`（env.py、script.py.mako、versions/0001_initial.py）、
  `alembic.ini`、`src/tests/{test_db_url,test_migrations,test_migration_tool,test_pg_acceptance}.py`
- 改造：`team_collab/{models.py,manager.py}`、`api/review/review_history.py`、
  `baa_engine/collab/audit.py`、`baa_engine/cache.py`、`src/tests/conftest.py`、
  `pyproject.toml`（pg marker）、`requirements.txt`（alembic、psycopg[binary]）

## 过程修复缺陷

1. `session.execute(insert(Model), data)` 走 ORM bulk 路径返回 IteratorResult（无
   rowcount）→ 改 `session.connection().execute()` Core 路径
2. MIGRATION_PLAN 含协作域后加表（rectification_records 等），旧源库缺表直接崩溃 →
   增加源库缺表容错（error 标记 + 跳过）
3. alembic.ini 中文注释在 Windows GBK 下 UnicodeDecodeError → 英文注释
4. atexit 删 per-pid 测试库被池化连接锁定（WinError 32）→ conftest 退出前先
   `dispose_all()`
5. pytest 裸 SQL `text()` 直查 JSON 列只回 TEXT（绕过列类型）→ 单测断言改 ORM 模型读
   （T4 真实使用路径）
6. 真实 legacy 库存在孤儿审计行（旧 SQLite 不强制 FK），新 schema FK 约束下插入崩溃 →
   搬迁工具加 FK 守卫（guard）：孤儿行跳过并计入 `skipped`，行数比对口径同步修正
7. psycopg3 对 ON CONFLICT DO NOTHING 被忽略的插入返回 rowcount=-1（-634）→
   「inserted」改表级净增计数（迁移前后 count 差），驱动无关、语义更准
