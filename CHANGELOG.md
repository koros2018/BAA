# Changelog

## v1.12.0 (2026-06-26) — 原子函数扩展完成（30/30）+ L3规范+测试全覆盖

### 新增
- **11条 L3 规范条目** 到 spec_repository（对应全部 11 个 L3 原子函数）
  - 防火间距/排烟窗面积/消防电梯/消防电梯前室面积
  - 袋形走道长度/疏散出口宽度/防火窗等级
  - 消防水箱/消防水池/消防救援窗面积/应急广播
  - 全部含 civil/industrial 建筑类型阈值
- **22个 L3 原子函数测试**（每个函数 PASS/FAIL 双测试，EXIST 类含缺失检查）
  - DIST-002/DIM-008/EXIST-007/AREA-002/DIST-003
  - DIM-009/ATTR-003/EXIST-008/EXIST-009/DIM-010/EXIST-010
- **前端规范库显示 30 条规范**（10L1+10L2+11L3）

### 修复
- 前端引擎状态硬编码 "19/30" → 动态 "30/30"
- 概览页规范计数硬编码 "20" → 动态 SPEC_DATA.length

### 测试
- 97/97 全部通过（+22 新增 L3 测试）✅

## v1.11.0 (2026-06-26) — 部署准备（Docker/健康检查/DEPLOY.md）

### 新增
- **Dockerfile**: 多阶段构建，Python 3.12-slim 基础镜像，仅 150MB+
  - 构建阶段安装编译依赖，运行阶段只留运行时包
  - HEALTHCHECK 健康检查
  - Gunicorn + Uvicorn Worker 生产启动
- **docker-compose.yml**: 一键部署编排
  - 持久化数据卷 baa_data
  - 环境变量注入
  - 日志轮转（10MB x 3）
- **DEPLOY.md**: 部署指南（Docker 快速启动 / 配置说明 / 生产建议）
- **.dockerignore**: 排除开发/测试/数据文件

### 改进
- **增强健康检查端点**: 返回子系统状态（engine/spec/parser/yolo）
  - 支持 degraded 状态（部分子系统不可用时）
  - 增加启动时间记录
  - 返回数据目录信息
- **.env.example 完善**: 增加密钥配置、Docker 部署说明

### 测试
- 75/75 全部通过 ✅

## v1.10.0 (2026-06-26) — 前端体验优化（历史记录/分析图表/预览缩放）

### 新增
- **审查历史记录页**: 侧边栏新增「📋审查记录」页面，显示完整审查历史
  - 支持按图纸名称/规范编号搜索
  - 支持按建筑类型/违规状态筛选（民用/工业/有违规/全部合规）
  - 点击记录弹出详情弹窗（违规分布卡片+逐条详情）
  - 清空历史功能（带确认）
- **概览页增强**: 使用 reviewResults 真实数据
  - 统计卡片显示真实审查数量/通过率
  - 新增「最近审查」列表
  - 规范命中频率柱状图（自动统计 top8）
  - 违规类型分布柱状图（严重/主要/轻微）
- **结果分析页增强**: 
  - 审查趋势柱状图（最近10张违规数对比）
  - 违规分布柱状图（按严重度比例）
  - 分析表格显示建筑类型+审查时间
- **预览缩放**: 点击图纸渲染图片可全屏放大查看

### 改进
- 概览页/分析页数据源从 reviewHistory（未持久化）迁移到 reviewResults（localStorage 持久化）
- 分析表格增加「建筑类型」「审查时间」列
- 批量送审结果样式优化

## v1.9.5 (2026-06-25) — 密钥管理独立令牌+物理删除

### 修复
- **密钥管理页独立持管理令牌**: 新增 GET /admin/bootstrap-key 免认证端点，
  密钥管理页初始化时自动获取，不再依赖连接配置页 localStorage，
  解决"无令牌→无法创建admin→无法配置"的死循环
- **多worker下密钥加载不到**: _loaded 短路导致 delete_key/revoke_key
  读不到其他worker写入的密钥，提取 _reload() 跳过 _loaded
- **require_admin 开发模式不校验**: API_KEYS 为空时直接放行

### 新增
- **物理删除密钥**: DELETE /admin/keys/{key_id} 端点 + 前端 🗑️ 按钮
- **密钥验证端点**: POST /admin/keys/verify 无权限要求，导入流程先验证
- **API地址持久化**: localStorage 读写，刷新不丢失
- **连接配置页令牌删除按钮**: 选择器旁 🗑️

### 改进
- 刷新按钮/导入弹窗增加视觉反馈和错误提示
- 密钥管理页无令牌时顶部黄色/红色引导提示

### 测试
- 75/75 全部通过 ✅

## v1.9.0 (2026-06-24) — API密钥管理完善

### 新增
- **API密钥管理系统 `api_key_manager.py`**:
  - 密钥自动生成（secrets.token_urlsafe，baa_前缀）
  - 多密钥并行有效（支持轮换宽限期）
  - 密钥过期机制（可配置TTL，默认90天）
  - 4级权限：admin / write / read / limited
  - 用量统计：调用次数、最后使用时间、每分钟限流
  - JSON文件持久化（data/api_keys.json）
  - 过期自动清理
- **API密钥管理端点（6个admin端点）**:
  - POST /admin/keys — 创建密钥（返回raw_key仅一次）
  - GET /admin/keys — 列表（含用量）
  - POST /admin/keys/{id}/revoke — 撤销
  - POST /admin/keys/{id}/rotate — 轮换
  - GET /admin/keys/stats — 用量统计
- **测试**: 7个API密钥管理单元测试（13→13 API测试全部通过）

### 改进
- verify_api_key 集成 ApiKeyManager（支持多key、过期检查）
- 环境变量 BAA_API_KEY 仍作为admin通道保留

### 回归
- 75/75测试全部通过（62引擎 + 13 API）

## v1.8.6 (2026-06-24) — 合成图纸检出率 79.5%→100%

### 修复
- **合成图纸生成器 `generate_synthetic_v2.py`**:
  - LIGHT-001（应急照明）: 违规时也生成 evacuation_lighting 实体（照度0.5lx）
  - ATTR-002（保温材料）: 违规时也生成 insulation 实体（等级B2）
  - DIM-007（防火卷帘）: 新增 fire_curtain 实体生成（违规时宽度>10m）
  - DIM-002（防火分区面积）: 违规时强制大尺寸（≥55×50m，面积≥2750㎡）
- **测试基础设施**:
  - 新增 conftest.py（根目录+src/tests）
  - batch测试导入路径修复（src.baa_engine→baa_engine）
  - 检出率assert从50%→95%

### 回归
- 全量200张合成图纸: 626/626违规检出（**100%**）
- 19个原子函数全部100%检出
- 62/62单元测试全部通过

## v1.8.5 (2026-06-24) — door宽度推断+NaN防御+配电房全合规

### 修复
- **`_compute_bbox` 多层兜底**: ezdwg手动重建LWPOLYLINE从points计算、
  LINE从start/end端点计算、vertices()兼容多种坐标格式
- **LWPOLYLINE `_extract_properties`**: 增加point_count属性
- **`_classify_by_geometry`**: 2点LWPOLYLINE视为LINE等价（真实图纸适配）
- **`_infer_corridor_widths` 平行线聚类算法**:
  - 收集LINE/2点LWPOLYLINE，按方向分组（水平/垂直）
  - 统计平行线间距众数作为走廊宽度
  - 宽度单位mm→m转换
  - 空间分区：取最宽合适宽度作为主走廊宽度

### 基线提升（真实图纸）
- 泵房: 合规92→168（+83%）
- 配电房: 合规100→177（+77%）
- 室外电气: 合规175→264（+51%）
- 东莞通建筑: 合规217→411（+89%）
- 62/62单元测试全部通过

## v1.7.2 (2026-06-23) — 训练数据修复+前端增强+DWG解析三级兜底

### 修复
- **YOLO训练数据标注修复**: door/window/fire_door/fire_window 的bbox厚度从0.05→0.5，过滤阈值3px→2px
  - 标注总数从6,422→11,233，18个类别全部有标注
- **`/review-from-data`端点**: 兼容deconstruct返回的elements结构（缺少id字段时使用type兜底）

### 新增
- **DWG解析三级兜底** (`drawing_parser.py`)
  - Level 1: ezdwg.read() + export_dxf() 直转
  - Level 2: ezdwg Entity.dxf字典手动逐元素重建
  - Level 3: 文件头检测（AC10xx版本）+ 友好提示（建议用LibreCAD另存DXF）
  - 成功解析: 通风(88021图元)、建筑图(37412)、泵房(5875)、配电房(3576)、室外电气(19485)等
- **原子函数 `_extract_value` 单位转换优化**
  - 新增 unit 字段优先判断（mm/m/mm2/m2）
  - 面积转换阈值从粗糙的>=100改为>10000
  - 所有单位转换逻辑统一化
- **前端对比重构页面增强**
  - 概览摘要（合规率/违规数/修正数/实体数）
  - 违规可视化叠加（Canvas网格标注，按实体类型和严重度着色）
  - 修正后效果预览（按优先级分组显示修正操作）
- **前端DWG上传支持**: 解除.dxf格式限制，允许.dxf/.dwg双格式上传

### 测试
- 60/60单元测试全部通过
- 合成图纸200张批量回归: 79.5%检出率（较v1.7.1的70%提升9.5个百分点）
- 全链路测试（上传→解析→审查→修正）通过
- civil/industrial分布验证通过

### 进行中
- YOLOv8n V3训练（200 epochs, CPU, 当前105/200）