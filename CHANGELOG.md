# Changelog

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