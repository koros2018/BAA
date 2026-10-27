# D3-T3 客户成功流程 SOP 方案

> **来源**：`docs/roadmap-phase-d-execution-plan.md` 第 3 节 D3-T3  
> **Roadmap 验收**：定义"新客户接入 → 首次审查 → 整改闭环 → 续约"全流程并落库  
> **写作日期**：2026-10-27  
> **前置**：T-B6（审查/整改闭环）、D3-T1/D3-T2（交付物模板化）  
> **本方案范围**：D3-T3（流程文档 + review_projects 表 + API + 端到端跑通）

---

## 1. 现状分析

### 1.1 已交付能力
- **审查闭环**：`review_history` 表记录审查任务，但无项目维度聚合
- **整改闭环**：`audit.status=confirmed` + 复查字段（T-B6）
- **交付物**：D3-T1 报告模板 + D3-T2 整改通知单 Word

### 1.2 缺失能力
- **无项目表**：审查记录散落在 `review_history`，无法按项目追踪生命周期
- **无 SOP 文档**：客户成功流程未成文
- **无项目状态机**：onboarding → first_review → correction → recheck → closed 无状态跟踪

---

## 2. 改造目标

### 2.1 Roadmap DoD
- [ ] `docs/customer-success-sop.md`：onboarding 6 步、首轮审查 3 步、整改闭环 4 步、续约触发条件
- [ ] DB `review_projects` 表：`project_id` / `customer_name` / `standard_set_code` / `owner` / `status`
- [ ] `POST /projects` + `PATCH /projects/{id}/status` 接口
- [ ] 端到端跑通：创建项目 → 首轮审查 → 整改 → 复查 → 归档

### 2.2 验收标准
| 验收项 | 标准 |
|--------|------|
| SOP 文档 | 覆盖 onboarding/审查/整改/续约全流程 |
| 项目表 | `review_projects` 表可创建/查询/更新状态 |
| API | POST /projects + PATCH /projects/{id}/status 返回 200 |
| 状态机 | onboarding → first_review → correction → recheck → closed 顺序流转 |
| 回归 | 全量后端测试 0 退化 |

---

## 3. 改造范围

### 3.1 阶段 A：DB 表 + SQL（0.5 天）
- `src/baa_engine/db/models/project.py`：`ReviewProject` ORM
- Alembic 迁移脚本

### 3.2 阶段 B：API 端点（0.5 天）
- `POST /api/v1/projects`：创建项目
- `GET /api/v1/projects`：列出项目
- `GET /api/v1/projects/{id}`：项目详情
- `PATCH /api/v1/projects/{id}/status`：更新状态

### 3.3 阶段 C：SOP 文档 + 测试（1 天）
- `docs/customer-success-sop.md`
- `test_projects.py`（6 用例）
- 全量回归

---

## 4. 状态机定义

```
onboarding → first_review → correction → recheck → closed
     ↓             ↓             ↓           ↓
    创建项目    完成审查      提交整改     复查通过
```

---

## 5. 关键设计

### 5.1 review_projects 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | str (UUID) | 主键 |
| project_name | str | 项目名 |
| customer_name | str | 客户名 |
| standard_set_code | str | 标准集 |
| owner | str | 负责人 |
| status | str | onboarding/first_review/correction/recheck/closed |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 更新时间 |

### 5.2 API
- `POST /api/v1/projects`：body `{project_name, customer_name, standard_set_code, owner}` → `{id, status}`
- `GET /api/v1/projects?status=xxx&limit=50`
- `GET /api/v1/projects/{id}`
- `PATCH /api/v1/projects/{id}/status`：body `{status}` → `{id, status, updated_at}`

---

## 6. 风险
- 状态机非法跳转（如 closed → first_review）：API 层校验并 400
- 项目删除影响历史审查：软删除（status=closed）

---

## 7. Checklist
- [ ] DB model + Alembic
- [ ] API 4 端点
- [ ] SOP 文档
- [ ] 6 个单测
- [ ] 全量回归
- [ ] commit
