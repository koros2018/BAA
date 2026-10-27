# D3-T4 交付物版本化 + SDK 兼容矩阵方案

> **来源**：`docs/roadmap-phase-d-execution-plan.md` 第 3 节 D3-T4  
> **Roadmap 验收**：交付物包有版本标记，SDK 对不同交付包版本做兼容  
> **写作日期**：2026-10-27  
> **前置**：D2-T3（离线导出 manifest.json 已有 report_schema_version）、T-C6（SDK KnowledgeBundle 已有 schema 主版本校验）  
> **本方案范围**：D3-T4（新增 ReportBundle 类 + VersionMismatchError + 兼容矩阵文档）

---

## 1. 现状分析

### 1.1 已交付
- **manifest.json 已有字段**：export_bundle.py 已写入 `report_schema_version` 和 `report_version`
- **KnowledgeBundle 已有 schema 校验**：`SCHEMA_MAJOR = 1`，加载时校验主版本，不匹配抛 `KnowledgeBundleError`
- **SDK 版本**：`__version__ = "2.5.80"`（pyproject.toml + __init__.py）

### 1.2 缺失能力
- **无 `ReportBundle` 类**：现有 `KnowledgeBundle` 用于知识库离线包（functions/specs/versions），无专用报告包类
- **无 `VersionMismatchError`**：schema 不匹配统一用 `KnowledgeBundleError`，语义不清
- **无兼容矩阵**：无 SDK 版本 × 交付物 schema 版本的对照表

---

## 2. 改造目标

### 2.1 Roadmap DoD
- [x] manifest.json 新增 `report_schema_version`（D2-T3 已交付）
- [ ] SDK 新增 `ReportBundle` 类，schema 版本不匹配抛 `VersionMismatchError`
- [ ] SDK 文档维护兼容矩阵（SDK 版本 × 交付物 schema 版本）

### 2.2 验收标准
| 验收项 | 标准 |
|--------|------|
| VersionMismatchError | 独立异常类，可被单独捕获 |
| ReportBundle.load | 加载 report zip（含 manifest.json），校验 schema_version 主版本 |
| 版本不匹配 | 抛 `VersionMismatchError` 而非 `KnowledgeBundleError` |
| 兼容矩阵 | README 有版本对照表，明确各 SDK 版本支持的 schema 范围 |
| 测试 | 3 个单测覆盖：正常加载 / schema 不匹配 / 文件缺失 |

---

## 3. 改造范围

### 3.1 阶段 A：新增 VersionMismatchError + ReportBundle（0.5 天）

**改动**：
1. `src/sdk/__init__.py` 新增：
   - `VersionMismatchError(BAAError)`：版本不匹配专用异常
   - `ReportBundle` 类：加载 report zip（含 manifest.json），校验 `schema_version` 主版本，不匹配抛 `VersionMismatchError`
2. `ReportBundle` 与 `KnowledgeBundle` 共享 BAAError 基类但异常不同，调用方可精确 catch

**ReportBundle 结构**：
```python
class ReportBundle:
    SCHEMA_MAJOR = 1

    def __init__(self, path, manifest):
        self.path = Path(path)
        self.manifest = manifest

    @classmethod
    def load(cls, path):
        # 1. 打开 zip
        # 2. 读取 manifest.json
        # 3. 校验 format == "baa-report-bundle"
        # 4. 校验 schema_version 主版本
        # 5. 返回 ReportBundle 实例
```

### 3.2 阶段 B：兼容矩阵文档（0.5 天）

**改动**：
- `src/sdk/README.md` 新增"交付物版本兼容矩阵"章节
- 表格：SDK 版本 × schema 版本

---

## 4. 关键设计

### 4.1 VersionMismatchError 继承关系
```
BAAError
├── KnowledgeBundleError
│   └── KnowledgeBundle 抛此异常
└── VersionMismatchError   ← 新增，ReportBundle 抛此异常
```

### 4.2 ReportBundle vs KnowledgeBundle
| 维度 | KnowledgeBundle | ReportBundle |
|------|----------------|--------------|
| 包格式 | baa-knowledge-bundle | baa-report-bundle |
| 核心文件 | functions.json, specs.json, versions.json | manifest.json（报告元数据） |
| 用途 | 离线知识库（审查引擎用） | 离线交付包（客户验收用） |
| Schema 版本 | SCHEMA_MAJOR=1 | SCHEMA_MAJOR=1 |
| 异常类型 | KnowledgeBundleError | VersionMismatchError |

### 4.3 兼容矩阵
| SDK 版本 | 支持的 report_schema_version | 支持的 kb_schema_version |
|----------|------------------------------|--------------------------|
| 2.5.80+  | 1.x                          | 1.x                      |
| 2.6.0+   | 1.x, 2.x                     | 1.x, 2.x                 |

---

## 5. 执行 Checklist
- [ ] `VersionMismatchError` 异常类
- [ ] `ReportBundle` 类（load/summary）
- [ ] 测试：正常加载 / schema 不匹配 / 文件缺失
- [ ] README 兼容矩阵
- [ ] 全量回归
