# Changelog

## v1.4.0 (2026-06-21) — 前端增强 + EMA2对接方案

### 新增
- **EMA2 × BAA 对接方案文档** (`docs/07-重大变更/工程可行性研究报告及设计（终稿）/EMA2×BAA对接方案.md`)
  - 完整API对接清单（5端点）
  - 异常处理对照表（8种错误码）
  - 任务全生命周期（审查→付费→重构→异常重试）
  - 环境配置指南
- **EMA2侧 baa_client.py** (`ema2_baa_client.py`)
  - 完整封装：health / deconstruct / review / reconstruct / check_order
  - 异常映射：error_code → Python异常类
  - 用户可见错误提示
  - run_full_flow 一键编排
  - 命令行模式

### 前端增强
- 概览页从 /health 获取实时状态
- 图纸管理支持上传并调用 /review
- AI审图页显示违规详情
- 规范库动态加载20条含 building_type
- 设置页可配置API地址/密钥
- 结果分析页显示审查历史

### API认证简化
- security = HTTPBearer(auto_error=False)
- 无API_KEY时不验证（开发模式）
- sys.path在模块级设置，确保引擎导入

## v1.3.0 (2026-06-21) — MCP Server + Skill 包（DD-9实现）

### 新增
- **MCP Server** (`src/mcp/baa_mcp_server.py`)
  - 3个工具：baa_deconstruct, baa_reconstruct, baa_review
  - 支持 stdio 和 streamable-http 两种传输模式
  - 懒加载引擎模块，building_type 参数，auth_token 授权验证
- **Skill 包** (`src/skill/`)
  - SKILL.md 使用说明
  - scripts/ 包含完整CLI工具（deconstruct/reconstruct/review）
  - baa_client.py BAA API 客户端封装
  - 支持环境变量和配置文件两种配置方式

### 测试
- MCP Server 初始化+工具列表+deconstruct调用全部通过
- Skill 命令行工具用法提示正确
- 真实图纸批量验证：东莞通建筑图 34748图元/962实体/4.58s

## v1.2.0 (2026-06-21) — 智能判定过滤

### 改进
- AtomicFunction 新增 target_entities 字段
- execute() 支持类型匹配，不匹配返回 None
- 19个函数全部配置了目标实体类型
- 过滤率 90.8%（76次检查→7次有效判定）
- API层判定循环适配 execute 返回 None

## v1.1.0 (2026-06-21) — 规范阈值按建筑类型区分 + L2扩展

### 新增
- Clause 支持 building_type 维度阈值（civil/industrial）
- 规范从10条扩展至20条（10L1 + 10L2）
- 原子函数从10个扩展至19个
- SpecRepository.get_threshold() 方法
- API端点 /deconstruct、/review 新增 building_type 参数
- 语义分析器返回 building_type 元数据

## v1.0.0 (2026-06-21) — V1.0 正式发布 🚀

### 新增
- BAA 核心引擎：10个原子函数 + 10条L1规范 + 语义识别 + 归因分析
- 图纸解析管线：ezdxf 集成，支持 DXF/DWG 格式
- YOLOv8n + LoRA 微调图元识别模型
- API 服务层：/deconstruct, /review, /reconstruct, /order, /health
- Web 前端：7页面单页应用（概览/图纸/规范/审图/对比/分析/设置）
- 授权验证：auth_token（HMAC-SHA256）+ 多密钥宽限期
- 规范JSON导出：data/specs/baa_specs_v1.json

### 修复
- 授权 token 时间比较：兼容带/不带时区的时间字符串
- 测试用例过期时间更新
- API 测试变量名对齐（AUTH_SECRET → AUTH_SECRETS）

### 基础设施
- 项目数据目录迁移至项目内 `data/`
- 日志输出至 `data/logs/baa-api.log`
- 5层测试体系全部通过（15项测试）
- 端到端审查：9620次检查 / 2.5秒
- 性能基线：1.8s < 10s 目标 ✅

### 已知限制
- DWG 转换后图层信息丢失，几何兜底是唯一有效分类方式
- 训练数据仅1张真实图纸，LoRA 微调数据量不足
- 规范阈值未按建筑类型区分（工业/民用）
