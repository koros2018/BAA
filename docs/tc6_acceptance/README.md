# T-C6 知识库开放 — 验收证据链

日期：2026-10-25　分支：main

## 1. 目标与范围

Roadmap 阶段 C 的 T-C6「知识库开放」：原子函数/规范 schema 版本化 + SDK 示例。

验收标准（roadmap）：

- [x] 一键导出知识库包。
- [x] SDK 10 分钟内跑通（含示例）。

## 2. 实现设计

### 2.1 schema 版本化

| 常量 | 位置 | 语义 |
|---|---|---|
| `KB_FORMAT = "baa-knowledge-bundle"` | `src/baa_engine/knowledge.py` | 包格式标识，非该值一律拒绝 |
| `KB_SCHEMA_VERSION = "1.0"` | 同上 | **包结构与字段契约**版本；主版本变更=不兼容 |
| `KB_VERSION = "1.0.0"` | 同上 | 知识库**内容**版本（原子函数 + 条文集合） |

强制点（两侧各一）：

- 服务端 `read_bundle_manifest()`：导出后自校验，schema 主版本不符即报错。
- SDK `KnowledgeBundle.load()`：校验 format → schema 主版本（`SCHEMA_MAJOR=1`）→ 各文件 sha256 → 条目计数，任一不符抛 `KnowledgeBundleError`。

字段契约由 `test_schema_contract_fields` 固化：每条原子函数必须含
`func_id/name/description/category/clause_id/target_entities/operator/threshold/unit/depends_on`，
每条规范条文必须含 `clause_id/standard/title/text/level/func_id/category/params`。

### 2.2 一键导出知识库包

```
python -m src.baa_engine.knowledge -o dist/baa_knowledge.zip
```

产物 zip（4 文件）：

| 文件 | 内容 |
|---|---|
| `manifest.json` | format / schema_version / kb_version / generated_at / counts / standards / 每文件 sha256 |
| `functions.json` | 原子函数清单（分类、条款关联、阈值、目标实体、依赖、是否需全局上下文） |
| `specs.json` | 规范条文（标准、层级、关联原子函数、结构化阈值含按建筑类型分档） |
| `versions.json` | 规范版本元数据 + 变更日志（GB50016 2014→2025 / NFPA101 2021→2024） |

实测：**422 条原子函数 / 199 条条文 / 8 套标准 / 34,531 bytes**。

### 2.3 SDK 示例（10 分钟跑通）

| 文件 | 说明 |
|---|---|
| `src/sdk/__init__.py` | 新增 `KnowledgeBundle`（离线加载 + 完整性校验）、`spec_versions()` 在线方法、`__version__ = 2.5.80` |
| `src/sdk/examples/quickstart_offline.py` | 无需服务：包缺失时自动一键导出 → 加载校验 → 查询示例 |
| `src/sdk/examples/quickstart_online.py` | 连服务：health → functions → specs → spec_versions |
| `src/sdk/README.md` | 新增「10 分钟跑通」「知识库包（离线）」章节 + 端点表补 `spec_versions` |

### 2.4 阻塞项修复：SDK 原本无法安装

实测 `pip wheel src/sdk` 直接失败（`BackendUnavailable: Cannot import 'setuptools.backends._legacy'`）。三处元数据缺陷：

| 缺陷 | 现象 | 修复 |
|---|---|---|
| `build-backend = "setuptools.backends._legacy:_Backend"` | 该后端不存在，构建直接崩 | 改 `setuptools.build_meta` |
| `py-modules = ["baa_sdk"]` | 实际是 `src/sdk/__init__.py`（无 `baa_sdk.py`），模块找不到 | 改 `packages=["baa_sdk"]` + `package-dir = {baa_sdk = "."}` |
| `dependencies = {file = ["requirements.txt"]}` | `src/sdk/requirements.txt` 不存在 | 改 `dependencies = []`（httpx 降为 optional `http`，保留 urllib 回退） |

修复后 `baa_sdk-2.5.80-py3-none-any.whl` 构建成功，安装后 `import baa_sdk` 可用并能加载知识库包。

## 3. 验收结果

| 验收项 | 证据 | 结果 |
|---|---|---|
| 一键导出知识库包 | `python -m src.baa_engine.knowledge -o ...` 退出码 0，产物 4 文件、sha256 自校验通过 | **达标** |
| SDK 10 分钟内跑通（含示例） | `python src/sdk/examples/quickstart_offline.py` 从零导出并跑通，全程无需网络与服务；wheel 构建 + 临时目录安装 + `import baa_sdk` + `KnowledgeBundle.load` 实测通过 | **达标** |
| schema 版本化 | 主版本不兼容 / 校验和不匹配 / 缺文件 / format 不符 四类拒绝用例全过 | **达标** |
| 单测 | `test_knowledge_export.py` **12 passed** | 达标 |
| 全量回归 | **2578 passed / 0 failed / 22 skipped**（基线 2566 + 12，见 regression.txt） | 达标 |

实测命令与输出：

```
$ python -m src.baa_engine.knowledge --output D:\tmp\kb_test.zip
输出: D:\tmp\kb_test.zip
schema_version: 1.0  kb_version: 1.0.0
计数: functions=422 specs=199 standards=8
大小: 34531 bytes

$ python src/sdk/examples/quickstart_offline.py
[1/3] 知识库包不存在，执行一键导出 -> ...\dist\baa_knowledge_v1.0.0.zip
[2/3] 加载并校验知识库包: ...dist\baa_knowledge_v1.0.0.zip
      schema=1.0 kb=1.0.0 生成于 2026-10-25T13:23:48+00:00
      原子函数 422 条 / 规范条文 199 条 / 标准 8 个
[3/3] 查询示例
      原子函数示例: DIM-001 - 疏散楼梯净宽判定（dim）
        关联条款: GB50016-5.5.18  判定: >= 1.2m
[OK] 离线示例跑通（全程无需网络与服务）

$ python -m pip wheel src/sdk --no-deps -w D:\tmp\wheelout
Successfully built baa-sdk   → baa_sdk-2.5.80-py3-none-any.whl
$ pip install ...whl -t D:\tmp\sdk_inst && python -c "import baa_sdk; ..."
version: 2.5.80
has KnowledgeBundle: True
installed SDK loads bundle: {'functions': 422, 'specs': 199, 'standards': 8}
```

## 4. 已知限制

- 知识库包体积小（34 KB）源于原子函数/条文为结构化规则摘要，不含规范原文全文；
  全文分发涉及标准版权，需单独立项评估。
- `specs.json` 中 199 条条文与 422 条原子函数并非一一对应（部分函数为通用判定，
  无绑定条款），属既有数据形态，未在本次调整。
- SDK 暂未发布到 PyPI；`pip install baa-sdk` 需仓库内 `pip install ./src/sdk` 或预构建 wheel。
- `dist/` 与 `src/sdk/build/` 已加入 `.gitignore`，导出产物不入库。
