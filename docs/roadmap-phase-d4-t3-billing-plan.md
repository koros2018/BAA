# D4-T3 用量计费 + 支付集成方案

> **来源**：`docs/roadmap-phase-d-execution-plan.md` 第 4 节 D4-T3  
> **Roadmap 验收**：Web 端用量统计 → 结算 → 在线购买 → 自动续期  
> **写作日期**：2026-10-27  
> **前置**：T-C2（api_key_usage 已交付）、D4-T1（定价文档）、D4-T2（License 模块）  
> **本方案范围**：D4-T3（billing_cycles 表 + 结算任务 + Stripe/微信支付回调 + 试用机制），不含前端 UI

---

## 1. 现状分析

### 1.1 已有能力
- `api_key_usage` 表：`key_id`（PK）+ `calls`（累计调用次数）+ `last_used`
- `rate_limit_buckets` 表：固定窗口限流
- License 模块（D4-T2）：已读取 license 文件，可获取 plan/max_monthly_reviews

### 1.2 缺失能力
- ❌ 无计费周期（billing cycle）概念
- ❌ 无超额检测与告警
- ❌ 无支付集成（Stripe / 微信支付）
- ❌ 无试用激活逻辑

---

## 2. 改造目标与验收标准

### 2.1 Roadmap DoD
- [x] `billing_cycles` 表：cycle_id / api_key / start / end / review_count / rate / amount_due / status
- [x] 结算任务：每日 0 点后台任务，按上一 cycle 统计用量，触发超额告警
- [x] 支付集成：Stripe Checkout（海外）+ 微信支付 Native 下单（国内），回调更新 status=paid
- [x] 试用：首次创建 api_key 自动激活 14 天试用，到期降级
- [x] SDK 查询：`api_key.get_billing_summary()` 返回当前 cycle 用量

### 2.2 本方案验收标准
| 验收项 | 标准 |
|--------|------|
| billing_cycles 表 | SQLAlchemy 模型 + Alembic 迁移 |
| 结算任务 | `schedule_billing_cycle()` 可手动触发，产出 billing summary |
| 超额告警 | review_count > max_monthly_reviews 时记录告警日志 |
| Stripe 回调 | `POST /api/v1/payments/stripe/webhook` 处理 checkout.session.completed |
| 微信支付回调 | `POST /api/v1/payments/wechat/webhook` 处理支付成功 |
| 试用激活 | `create_api_key()` 自动设置 14 天试用 |
| SDK 方法 | `get_billing_summary(key_id)` 返回 {review_count, cycle_start, cycle_end, amount_due} |
| 测试 | `test_billing.py` 5 用例全过 |

---

## 3. 数据模型

### 3.1 billing_cycles 表
```python
class BillingCycle(Base):
    __tablename__ = "billing_cycles"
    cycle_id = Column(String(64), primary_key=True)  # UUID
    key_id = Column(String(64), ForeignKey("api_keys.key_id"), nullable=False)
    start = Column(String(40), nullable=False)        # ISO 8601
    end = Column(String(40), nullable=False)          # ISO 8601
    review_count = Column(Integer, nullable=False, default=0)
    rate = Column(Float, nullable=False, default=0.0)  # 每张图纸单价
    amount_due = Column(Float, nullable=False, default=0.0)
    status = Column(String(20), nullable=False, default="open")  # open|paid|overdue|cancelled
    paid_at = Column(String(40), nullable=True)
    payment_intent_id = Column(String(200), nullable=True)  # Stripe session ID / 微信订单号
```

### 3.2 billing_alerts 表（可选，用于告警日志）
```python
class BillingAlert(Base):
    __tablename__ = "billing_alerts"
    alert_id = Column(String(64), primary_key=True)
    key_id = Column(String(64), nullable=False)
    cycle_id = Column(String(64), nullable=False)
    alert_type = Column(String(50), nullable=False)  # over_limit|payment_failed|trial_expired
    message = Column(String(500), nullable=False)
    created_at = Column(String(40), nullable=False)
```

---

## 4. 改造范围（分阶段）

### 阶段 A：billing_cycles 模型 + 迁移（0.5 天）
- 新建 `src/baa_engine/db/models/billing.py`
- 新建 `alembic/versions/xxx_add_billing_cycles.py`
- 新建 `src/baa_engine/billing_service.py`：`BillingService` 类（create_cycle、update_review_count、get_summary）

### 阶段 B：结算任务 + 超额告警（0.5 天）
- `billing_service.schedule_billing_cycle()`：结束当前 cycle → 统计用量 → 计算费用 → 开启新 cycle
- 超额告警：`review_count > max_monthly_reviews` → 写入 billing_alerts

### 阶段 C：支付回调（1 天）
- `POST /api/v1/payments/stripe/webhook`：处理 checkout.session.completed
- `POST /api/v1/payments/wechat/webhook`：处理支付成功
- 更新 billing_cycles.status = "paid" + paid_at

### 阶段 D：试用机制（0.5 天）
- `create_api_key()` 自动设置 14 天试用（trial=true in license）
- 试用到期检查：`trial_expires_in_days() == 0` → 降级为免费

### 阶段 E：SDK 方法（0.5 天）
- `src/sdk/baa_sdk/client.py` 新增 `get_billing_summary(key_id)` 方法

### 阶段 F：测试（0.5 天）
- `src/tests/test_billing.py`：5 个用例

**总计**：3.5 天

---

## 5. API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/billing/cycles` | GET | 查询当前计费周期 |
| `/api/v1/billing/summary` | GET | 当前周期用量摘要 |
| `/api/v1/payments/stripe/webhook` | POST | Stripe 支付回调 |
| `/api/v1/payments/wechat/webhook` | POST | 微信支付回调 |
| `/api/v1/payments/create-checkout` | POST | 创建支付（内部用） |

---

## 6. 风险与注意事项

- **支付安全**：Webhook 需验签（Stripe signature header / 微信签名），防止伪造回调
- **幂等性**：支付回调可能重复，需幂等处理（通过 payment_intent_id 去重）
- **时区**：billing cycle 按 UTC 计算，避免跨时区问题
- **Stripe 测试模式**：开发环境使用 test keys，生产环境切换 live keys

---

## 7. 依赖
- D4-T1（定价文档）→ 确定 rate（单价）
- D4-T2（License 模块）→ 获取 max_monthly_reviews
