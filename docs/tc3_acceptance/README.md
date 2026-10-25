# T-C3 可观测 — 验收证据链

日期：2026-10-25　分支：main

## 1. 目标与范围

Roadmap 阶段 C 的 T-C3「可观测」：接入 `/metrics`（Prometheus）+ 结构化日志 + 告警规则。

验收标准（roadmap）：

- 关键链路均有指标与告警（解析/判定/API）。
- 日志结构化可检索，告警可触达。

## 2. 实现设计

### 2.1 指标（`src/baa_engine/observability.py`）

| 链路 | 指标 | 标签 | 类型 |
|---|---|---|---|
| API | `baa_http_requests_total` | method/route/status | Counter |
| API | `baa_http_request_duration_seconds` | method/route | Histogram |
| 解析 | `baa_parse_duration_seconds` / `baa_parse_total` | result(success/failed) | Histogram + Counter |
| 判定 | `baa_review_duration_seconds` / `baa_findings_total` / `baa_review_errors_total` | endpoint / severity / code | Histogram + Counter×2 |
| 限流 | `baa_rate_limit_rejected_total` | — | Counter |
| 队列 | `baa_queue_{queued,running,completed,failed}` | — | Gauge（采集时回调 provider） |

关键取舍：

- **路由模板分组**：`MetricsMiddleware`（`src/api/metrics_middleware.py`）用
  `scope["route"].path` 作标签值（如 `/order/{order_id}`），防止路径参数造成标签基数爆炸；
  404/未知路径回退首两段。已用测试验证 raw 参数值不出现在指标里。
- **队列 Gauge 采集时刷新**：`register_queue_stats_provider` 由 lifespan 注入
  `_review_queue.stats`，`/metrics` 渲染前调用；provider 异常不影响其他指标输出。
- **多副本语义**：指标进程内聚合，Prometheus 按 Pod 抓取后 sum 聚合；
  `baa_queue_queued/completed/failed` 为命名空间全局读数（T-C2 队列已 DB 化），
  `running` 为本副本视角。
- 打点位置：`/deconstruct`（解析 Step1 + 判定 Step3）、`/review` 与 `/review-from-data`
  （解析 Step1、QUEUE_TIMEOUT/PARSE_FAILED 错误、判定完成时 findings 按 severity 计数）、
  `_enforce_rate_limit`（429 拒绝计数）。

### 2.2 结构化日志

- `JsonFormatter`：JSON 行（ts/level/logger/message + extras + exception），
  `log_request` 输出带 method/route/status/duration_ms/client 的访问日志。
- 默认人类可读格式不变；`BAA_LOG_FORMAT=json` 时 lifespan 切换 root logger 为 JSON。
- 可被 Loki/ELK 按字段检索（如 `{logger="baa.access"} | json | route="/review"`）。

### 2.3 告警规则（`k8s/prometheus-rules.yaml`，PrometheusRule CRD）

3 组 7 条，覆盖关键链路：

| 组 | 告警 | 条件 | 级别 |
|---|---|---|---|
| baa.api | BaaHighErrorRate | 5xx 比率 > 5%（5m） | critical |
| baa.api | BaaSlowRequests | /review、/deconstruct p95 > 120s | warning |
| baa.api | BaaPodDown | up 指标缺失 3m | critical |
| baa.pipeline | BaaParseFailureSpike | 解析失败率 > 20%（10m） | warning |
| baa.pipeline | BaaReviewSlowP95 | 判定 p95 > 300s | warning |
| baa.capacity | BaaQueueBacklog | 排队任务 > 20（10m） | warning |
| baa.capacity | BaaRateLimitSpike | 429 拒绝速率 > 1/s | info |

抓取配置：`baa-deployment.yaml` Pod 模板加 `prometheus.io/scrape|port|path` 注解。
触达路径：Prometheus → Alertmanager（receiver 由集群侧配置，webhook 可对接飞书/钉钉，
复用 T-B 已有 `webhooks.py` 的卡片格式）。

## 3. 验收结果

### 3.1 单测（`src/tests/test_observability.py`，9 用例全过）

| 用例 | 验证点 |
|---|---|
| counters_and_render | 8 个指标全部出现在 `/metrics` 文本输出 |
| queue_gauges_from_provider | provider 读数正确落入 4 个 Gauge |
| provider_failure_does_not_break_render | provider 异常时渲染不中断 |
| json_formatter | JSON 行含 level/logger/自定义字段且可 `json.loads` |
| structured_logging_json_mode | `BAA_LOG_FORMAT=json` 正确挂载 JSON handler |
| structured_logging_default_off | 默认不改动既有日志配置 |
| metrics_endpoint_exposed | `/metrics` 200 + 中间件自记录（第二次抓取可见） |
| route_template_not_raw_path | `/order/obs-test-12345` → 标签为 `/order/{order_id}`，raw 值不泄漏 |
| alert_rules_yaml_valid | PrometheusRule 结构合法、7 条告警齐、每条有 expr/for |

### 3.2 回归

- 全量：`2546 passed / 0 failed / 22 skipped`（基线 2537 + 新增 9，见 `regression.txt`）
- 实测 `/metrics` 端点输出含 `baa_http_requests_total{method="GET",route="/metrics",status="200"}`

## 4. 已知限制

- 单 worker + 多副本部署模型下用默认 REGISTRY 即可；若未来启用 Gunicorn 多 worker，
  需切 prometheus-client 多进程模式（`PROMETHEUS_MULTIPROC_DIR`）。
- 告警 receiver 属集群侧配置，不在本仓库（规则已就绪，接 Alertmanager 即可触达）。
- `/metrics` 未鉴权（Prometheus 抓取惯例，集群内网络收敛；如需收敛可加网络策略）。
