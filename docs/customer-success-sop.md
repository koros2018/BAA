# 客户成功流程 SOP（D3-T3）

> **适用对象**：客户成功团队 / 销售 / 项目交付  
> **版本**：v1.0（2026-10-27）

## 1. 概述

本 SOP 定义 BAA 智能审查平台从**客户接入**到**续约**的全流程，覆盖 5 个生命周期阶段，关键节点通过 `review_projects` 表落库，支持状态追踪与看板统计。

```
onboarding → first_review → correction → recheck → closed
   (接入)     (首轮审查)     (整改)      (复查)     (归档/续约)
```

---

## 2. 阶段 1：Onboarding（客户接入）—— 6 步

1. **需求确认**：明确项目范围（建筑类型、图纸数量、适用标准集）
2. **合同签约**：确认服务范围、SLA、定价
3. **账号开通**：创建 API Key、分配团队权限
4. **标准集配置**：选择国标/地标（如 CN-National-v1 / CN-Shanghai-v1）
5. **图纸规范确认**：确认图层命名、实体类型、DPI 要求
6. **联调测试**：1 张样图跑通审查 → `review_projects.status = first_review`

**交付物**：客户接入确认书 + 标准集配置单

---

## 3. 阶段 2：首轮审查 —— 3 步

1. **批量审查**：按 `POST /review` 上传图纸或 `POST /review-from-data` 提交实体
2. **结果确认**：与客户共同确认违规清单（critical/major/minor）
3. **报告交付**：生成 PDF 审查报告（D3-T1 模板）+ 交付 zip（D2-T3）

**状态流转**：`first_review → correction`（存在违规需整改）或 `first_review → closed`（零违规）

**交付物**：PDF 审查报告 + 整改通知单 Word（D3-T2）

---

## 4. 阶段 3：整改闭环 —— 4 步

1. **整改通知单下发**：`POST /api/v1/corrections/{review_id}/notice` 下载 Word
2. **客户整改**：客户按通知单修改图纸
3. **整改提交**：客户重新上传图纸
4. **复查触发**：`POST /api/v1/corrections/{review_id}/recheck` 下载复查意见 Word

**状态流转**：`correction → recheck`

**交付物**：整改通知单 Word + 复查意见 Word

---

## 5. 阶段 4：复查 —— 3 步

1. **复查执行**：重新审查整改后图纸
2. **结果确认**：
   - 全部通过 → `recheck → closed`
   - 仍有违规 → `recheck → correction`（循环整改）
3. **复查意见交付**：复查对照表 Word

**交付物**：复查意见 Word（含通过/不通过/待补对照表）

---

## 6. 阶段 5：归档与续约

### 6.1 归档
- 项目所有审查记录归档到 `review_projects`（status=closed）
- 交付物包（DXF + PDF + IFC + STEP + manifest）永久留存

### 6.2 续约触发条件
- 合同到期前 30 天
- 项目图纸审查次数 ≥ 10 张/月
- 客户主动提出新增标准集需求
- 客户提出新建筑类型审查需求

**续约流程**：新签合同 → 创建新项目（新 `review_projects` 记录）→ onboarding

---

## 7. 关键指标（SLA）

| 指标 | SLA |
|------|-----|
| 审查响应时间 | ≤ 30s/张（普通图纸） |
| 整改通知单生成 | ≤ 10s |
| 系统可用性 | ≥ 99.9% |
| 误报率 | ≤ 5% |
| 漏报率 | ≤ 1% |

---

## 8. 异常处理

| 场景 | 处理 |
|------|------|
| 客户图纸格式不规范 | 要求重新提交符合 DXF R2018+ 格式 |
| 审查超时 | 转异步队列，邮件通知 |
| 误报申诉 | `POST /api/v1/feedbacks` 提交，24h 内响应 |
| 系统不可用 | 降级为离线知识库包（T-C6） |

---

## 9. API 速查

| 操作 | 方法 | 路径 |
|------|------|------|
| 创建项目 | POST | `/api/v1/projects` |
| 列出项目 | GET | `/api/v1/projects?status=xxx` |
| 项目详情 | GET | `/api/v1/projects/{id}` |
| 更新状态 | PATCH | `/api/v1/projects/{id}/status` |
| 整改通知单 | POST | `/api/v1/corrections/{review_id}/notice` |
| 复查意见 | POST | `/api/v1/corrections/{review_id}/recheck` |
| 离线导出 | POST | `/exports/{review_id}` |
