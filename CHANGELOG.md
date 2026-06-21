# Changelog

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
