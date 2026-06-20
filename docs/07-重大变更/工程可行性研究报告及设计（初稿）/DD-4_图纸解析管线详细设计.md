# DD-4：图纸解析管线——详细设计文档

> **所属阶段：** 工程设计（详细设计）
> **对应架构层：** 图纸解析层 → 语义识别层
> **编制日期：** 2026-06-09
> **批准依据：** Master批准（专家评审决策会纪要修订版）
> **前提约束：** 零成本创业模式，所有实现基于开源工具+论文方法论

---

## 1. 设计概述

### 1.1 设计目标

将CAD图纸（DXF/DWG）转换为结构化图纸数据，供原子函数层进行合规判定。

**核心指标：**
- 图元识别准确率（L1级）：**≥85%**（参考1论文在CK+上达89.7%，迁移后取保守值）
- 尺寸标注提取准确率：**≥95%**（CAD原生数据）
- 单张图纸处理时间：**≤10秒**

### 1.2 参考来源

| 参考来源 | 贡献模块 | 迁移程度 |
|---------|---------|---------|
| 参考1论文4.1.2 数据增强 | 合成图纸数据生成 | 🟢 直接复用 |
| 参考1论文4.3.2 残差模块 | 图元识别backbone | 🟢 直接复用 |
| 参考1论文4.3.3 注意力模块 | 图元关键区域聚焦 | 🟢 直接复用 |
| 参考1论文4.4 训练策略 | 训练配置默认值 | 🟢 完全复用 |
| 论文#5 (DoorDet) | 多类门检测 | 🟢 参考设计 |
| 论文#14 (GLSP) | GNN线段解析+合成数据 | 🟡 参考设计 |
| 论文#8 (Fine-Tuning LLM) | LoRA微调策略 | 🟢 完全复用 |
| 论文#11 (RADIANT-LLM) | RAG规范检索 | 🟡 适配后复用 |
| 现有TECH_PLAN.md | ezdxf解析+LibreDWG转换 | 🟢 已有实现 |
| 可研报告v3.0 | 架构四层定义 | 🟢 约束条件 |

---

## 2. 管线架构

### 2.1 总管线图

```
输入图纸 (DXF/DWG)
    │
    ▼
┌──────────────────────────────────────────────────┐
│  Step 1: 基础几何解析                             │
│  (ezdxf parse_dxf_file → 图元/图层/尺寸标注)      │
│  参考: TECH_PLAN现有实现, 已有代码                  │
└───────────────────┬──────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────┐
│  Step 2: 语义图元识别                             │
│  ├── Backbone: ResNet (参考1论文4.3.2)            │
│  ├── Attention: 通道+空间注意力 (参考1论文4.3.3)   │
│  ├── Detection Head: YOLOv8 (参考论文#5 DoorDet)  │
│  ├── LoRA微调: 3-5张真实图纸 (决策DD-07)           │
│  └── 输出: 图元类别 + 边界框 + 置信度              │
│  参考: 参考1论文第四章完整框架                       │
└───────────────────┬──────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────┐
│  Step 3: RAG规范检索 (新增——决策DD-02, DD-11)     │
│  ├── Whoosh全文检索: 按条款编号/关键词精确检索      │
│  ├── Qwen2-1.5B辅助: 规范文本→JSON初稿生成         │
│  └── master审核回路: 确认后写入规范JSON库           │
│  参考: 论文#11 RADIANT-LLM精简版                   │
└───────────────────┬──────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────┐
│  Step 4: 几何参数提取                             │
│  (从识别结果提取尺寸/位置/属性 → 原子函数参数)      │
│  参考: DD-1原子函数参数定义                        │
└───────────────────┬──────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────┐
│  Step 5: 结构化图纸数据                            │
│  (JSON格式 → 原子函数判定引擎)                     │
│  包含: 图元列表 + 关系图 + 归因元数据               │
└──────────────────────────────────────────────────┘
    │
    ▼
原子函数判定 (DD-1 / DD-3)
```

### 2.2 各Step输入输出规范

| Step | 输入 | 处理 | 输出 | 预估耗时 |
|------|------|------|------|---------|
| 1 | DXF/DWG文件 (≤50MB) | ezdxf解析 | RawDrawingData (图元/图层/标注) | 1-3秒 |
| 2 | RawDrawingData | YOLOv8+Attention+LoRA | SemanticsData (图元类别/位置/置信度) | 3-5秒 |
| 3 | 规范查询请求 | Whoosh+Qwen2-1.5B+master审核 | SpecJSON初稿 (待确认) | 10-30秒(含审核) |
| 4 | SemanticsData | 原子函数参数提取 | ExtractedParams (尺寸/距离/属性) | 1-2秒 |
| 5 | ExtractedParams | 结构化组装 | StructuredDrawing (JSON) | <1秒 |

---

## 3. Step 1：基础几何解析（详细设计）

### 3.1 设计决策

| 决策项 | 选择 | 理由 | 约束 |
|--------|------|------|------|
| 解析引擎 | ezdxf (Python) | 零成本、纯Python、已有实现 | DXF原生支持，DWG需转换 |
| DWG转换 | LibreDWG WASM (Node.js) | 零成本、已有实现 | 只读，不支持写回 |
| 输出格式 | Python dict → JSON序列化 | 与现有TECH_PLAN一致 | — |
| 异常处理 | 图纸损坏→返回错误码+具体原因 | 客户友好 | — |

### 3.2 提取要素清单

| 要素 | ezdxf方法 | 输出格式 | 优先级 |
|------|----------|---------|--------|
| 图层列表 | `doc.layers` | `[{"name": str, "color": int, "linetype": str}]` | P0 |
| 线段(LINE) | `modelspace.query('LINE')` | `[{"layer": str, "start": (x,y), "end": (x,y)}]` | P0 |
| 多段线(LWPOLYLINE) | `modelspace.query('LWPOLYLINE')` | `[{"layer": str, "vertices": [(x,y),...], "closed": bool}]` | P0 |
| 圆/弧(CIRCLE/ARC) | `modelspace.query('CIRCLE,ARC')` | `[{"layer": str, "center": (x,y), "radius": float}]` | P0 |
| 尺寸标注(DIMENSION) | `modelspace.query('DIMENSION')` | `[{"layer": str, "measurement": float, "text": str}]` | P0 |
| 文字(MTEXT/TEXT) | `modelspace.query('MTEXT,TEXT')` | `[{"layer": str, "text": str, "insert": (x,y)}]` | P0 |
| 块引用(INSERT) | `modelspace.query('INSERT')` | `[{"layer": str, "name": str, "insert": (x,y), "scale": (x,y)}]` | P1 |

### 3.3 异常处理

```python
def parse_drawing(file_path: str, file_type: str) -> RawDrawingData:
    """入口函数：解析图纸，返回原始图纸数据"""
    if file_type == 'dwg':
        dxf_content = convert_dwg_to_dxf(file_path)
        return parse_dxf_content(dxf_content)
    elif file_type == 'dxf':
        return parse_dxf_file(file_path)
    else:
        raise UnsupportedFormatError(f"不支持的文件格式: {file_type}")
```

---

## 4. Step 2：语义图元识别（详细设计）

### 4.1 整体架构（迁移自参考1论文第四章）

```
参考1论文: 人脸表情识别模型
├── 输入: 48×48/224×224 灰度/彩色图像
├── Backbone: 基础卷积 → 残差模块(跳跃连接)
├── Attention: 通道注意力+空间注意力
├── Head: 全连接层 → SoftMax → 7类表情
├── 训练: Adam + CrossEntropy + EarlyStopping + 数据增强
└── 结果: CK+数据集89.7%

BAA适配: 图纸图元识别模型
├── 输入: DXF解析后的图元特征图
├── Backbone: 残差模块 (保留参考1的跳跃连接结构)
├── Attention: 通道+空间注意力 → 聚焦楼梯/出口/防火分区等
├── Head: YOLOv8检测头 → 10-20类图元
├── LoRA微调: 3-5张真实图纸 (保留预训练知识+领域适应)
├── 训练: Adam + CrossEntropy + EarlyStopping + 数据增强
└── 目标: 图纸图元识别≥85%
```

### 4.2 模型结构

```python
class PrimitiveRecognitionModel(nn.Module):
    """图元识别模型，基于参考1论文4.3节架构改造"""
    
    def __init__(self, num_classes: int = 20):
        super().__init__()
        # 4.3.1 基础卷积模块 (参考1论文)
        self.conv1 = ConvBlock(3, 64, kernel_size=3)
        self.conv2 = ConvBlock(64, 128, kernel_size=3)
        
        # 4.3.2 残差模块 (参考1论文 - 跳跃连接)
        self.res_block1 = ResidualBlock(128, 256)
        self.res_block2 = ResidualBlock(256, 512)
        
        # 4.3.3 注意力模块 (参考1论文 - 通道+空间)
        self.attention = SpatialChannelAttention(512)
        
        # YOLOv8检测头
        self.detection_head = YOLOv8Head(512, num_classes)
    
    def forward(self, x):
        x = self.conv1(x)
        x = self.conv2(x)
        x = self.res_block1(x)
        x = self.res_block2(x)
        x = self.attention(x)  # 聚焦关键图元区域
        return self.detection_head(x)
```

### 4.3 注意力模块详细设计（参考1论文4.3.3节）

```python
class SpatialChannelAttention(nn.Module):
    """通道+空间注意力模块，迁移自参考1论文4.3.3节"""
    
    def __init__(self, channels: int, reduction: int = 16):
        super().__init__()
        # 通道注意力
        self.channel_avg = nn.AdaptiveAvgPool2d(1)
        self.channel_max = nn.AdaptiveMaxPool2d(1)
        self.channel_fc = nn.Sequential(
            nn.Linear(channels, channels // reduction),
            nn.ReLU(),
            nn.Linear(channels // reduction, channels)
        )
        # 空间注意力
        self.spatial_conv = nn.Conv2d(2, 1, kernel_size=7, padding=3)
    
    def forward(self, x):
        avg_out = self.channel_fc(self.channel_avg(x).squeeze())
        max_out = self.channel_fc(self.channel_max(x).squeeze())
        channel_weight = torch.sigmoid(avg_out + max_out).unsqueeze(-1).unsqueeze(-1)
        
        spatial_in = torch.cat([x.mean(dim=1, keepdim=True), 
                                x.max(dim=1, keepdim=True)[0]], dim=1)
        spatial_weight = torch.sigmoid(self.spatial_conv(spatial_in))
        
        return x * channel_weight * spatial_weight
```

### 4.4 可识别的图元类别清单（L1级）

| 类别ID | 图元名称 | 所属规范条款 | 识别难度 | 目标准确率 |
|--------|---------|------------|---------|-----------|
| C01 | 墙体(Wall) | 防火分区/隔墙 | 🟢 低 | ≥90% |
| C02 | 门(Door) | 疏散出口/防火门 | 🟢 低 | ≥85% |
| C03 | 窗(Window) | 自然排烟/采光 | 🟢 低 | ≥90% |
| C04 | 楼梯(Stair) | 疏散楼梯/宽度 | 🟡 中 | ≥85% |
| C05 | 疏散走道(EvacCorridor) | 疏散距离 | 🟡 中 | ≥80% |
| C06 | 防火分区(FireZone) | 分区面积 | 🟡 中 | ≥80% |
| C07 | 尺寸标注(Dimension) | 各类尺寸判定 | 🟢 低 | ≥95% |
| C08 | 安全出口(Exit) | 出口数量 | 🟢 低 | ≥90% |
| C09 | 防火门(FireDoor) | 防火门等级 | 🟡 中 | ≥80% |
| C10 | 消防电梯(FireElevator) | 消防电梯设置 | 🔴 高 | ≥75% |

### 4.5 训练配置（迁移自参考1论文4.4节）

| 配置项 | 参考1论文值 | BAA建议值 | 理由 |
|--------|-----------|----------|------|
| 优化器 | Adam | Adam | 自动学习率调整，减少调参 |
| 学习率 | 0.001 | 0.001 (LoRA: 0.0005) | LoRA微调使用更低学习率 |
| 损失函数 | CrossEntropyLoss | CrossEntropyLoss + CIoU | 检测任务需加定位损失 |
| BatchSize | 32 | 16-32 | 取决于硬件 |
| 训练轮数 | 50-100 (含早停) | 100 (含早停patience=10) | 参考1策略 |
| 学习率衰减 | StepLR | ReduceLROnPlateau | 更适应验证集表现 |
| 早停 | ✓ (patience=10) | ✓ (patience=15) | 防止过拟合 |
| 权重衰减 | 1e-4 | 1e-4 | 参考1已验证 |

### 4.6 LoRA微调策略（决策DD-07）

根据Master决策，用3-5张真实图纸做LoRA微调，论文#8验证微调提升29.5%。

#### 4.6.1 LoRA配置

```python
lora_config = {
    "r": 8,                    # LoRA秩，8为平衡值
    "alpha": 16,               # 缩放参数
    "dropout": 0.1,            # 防止过拟合
    "target_modules": [        # 微调的目标模块
        "q_proj",              # YOLOv8 backbone query投影
        "k_proj",              # key投影
        "v_proj",              # value投影
        "attention.conv"       # 注意力模块卷积层
    ],
    "trainable_params": "~2%", # 仅微调约2%参数
    "base_model": "yolov8m.pt" # YOLOv8中等规模预训练权重
}
```

#### 4.6.2 微调流程

```
Step 1: 加载YOLOv8预训练权重 (yolov8m.pt)
Step 2: 冻结除注意力模块外的全部参数
Step 3: 注入LoRA适配器（r=8, alpha=16）
Step 4: 用3-5张真实图纸 + 50张合成图纸训练（LR=0.0005）
Step 5: 评估→如果mAP@0.5 < 85%则增加合成数据
Step 6: 导出微调权重 (lora_weights.pth)
```

#### 4.6.3 预期收益

| 指标 | 无微调 | 3张真实微调 | 5张真实微调 | 论文参考 |
|------|:-----:|:----------:|:----------:|:-------:|
| 墙体识别 | 90% | 92% | 93% | — |
| 防火门识别 | 78% | 82% | 85% | — |
| 消防电梯识别 | 72% | 76% | 80% | — |
| **整体mAP** | **82%** | **86%** | **88%** | 论文#8: 53%→82.7% |

#### 4.6.4 训练数据准备

| 数据源 | 数量 | 标注方式 | 获取方式 |
|--------|:----:|---------|---------|
| 合成图纸 | 500-1000张 | ezdxf自动标注 | 合成数据生成器 |
| 真实图纸微调 | 3-5张 | 人工标注 | Master联系设计院 |
| 验证集 | 50张合成+2张真实 | — | 留出20%训练集 |
| 测试集 | 100张合成+3张真实 | — | 独立预留 |

**微调不增加推理时间：** LoRA适配器在推理时可合并到主模型权重。

---

## 5. Step 3：RAG规范检索（新增——决策DD-02, DD-11）

### 5.1 架构定位

RAG不参与原子函数判定，而是用于**规范文本→JSON初稿的生成辅助**：

```
用户选择规范条款
    │
    ▼
┌─────────────────────┐
│  全文检索            │ ← 按条款编号精确检索（P0）
│  (Whoosh)            │    关键词模糊检索（P1）
└─────────┬───────────┘    语义相似度兜底（P2）
          │
          ▼
┌─────────────────────┐
│  LLM辅助提取         │ ← Qwen2-1.5B (Ollama本地)
│  (条款→JSON初稿)     │    提取: 条件/阈值/单位/例外
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  master审核          │ ← 确认/修正JSON初稿
│  (human-in-loop)     │    确认后写入规范JSON库
└─────────────────────┘
```

### 5.2 技术选型

| 组件 | 选型 | 理由 | 成本 |
|------|------|------|------|
| 全文检索引擎 | Whoosh (Python) | 纯Python无外部依赖 | ¥0 |
| LLM辅助解析 | Qwen2-1.5B (Ollama) | 小模型本地部署，不依赖API | ¥0 |
| 规范文本存储 | JSON文件 + Whoosh索引 | 结构简单，不引入数据库 | ¥0 |

### 5.3 检索粒度

| 检索方式 | 优先级 | 适用场景 |
|---------|:-----:|---------|
| 条款编号精确检索 | P0 | 已知条款号（如"GB50016-5.5.18"） |
| 关键词模糊检索 | P1 | 不确定条款号（如"疏散楼梯宽度"） |
| 语义相似度检索 | P2 | 复杂条件查询（如"高层住宅楼梯宽度要求"） |

---

## 6. 合成数据生成方案

### 6.1 数据增强策略（迁移自参考1论文4.1.2节）

| 增强方法 | 参考1论文 | BAA适配 | 参数建议 |
|---------|---------|--------|---------|
| 随机旋转 | ±15° | ±30° | 图纸朝向多变，范围更大 |
| 水平翻转 | ✓ | ✓ | 对称布局的变体 |
| 平移 | ±10% | ±20% | 图纸中图元位置偏移大 |
| 缩放 | 0.8-1.2 | 0.7-1.3 | CAD图纸比例多样 |
| 亮度/对比度 | ✓ | →图层颜色变体 | 不同设计院配色 |
| 高斯噪声 | σ=0.01 | σ=0.02 | 手绘CAD精度差异 |
| **新增：** 图层随机化 | — | ✓ | 随机合并/拆分图层 |
| **新增：** 标注扰动 | — | ✓ | 标注文字微小偏移 |

### 6.2 合成数据生成工具

```python
def generate_synthetic_drawing(output_path: str, config: DrawingConfig):
    """用ezdxf自动生成带标注的合成图纸"""
    doc = ezdxf.new('R2010')
    msp = doc.modelspace()
    
    walls = generate_walls(msp, config)
    doors, windows = generate_openings(msp, config, walls)
    stairs = generate_stairs(msp, config)
    dimensions = generate_dimensions(msp, walls, doors)
    organize_layers(doc, walls, doors, windows, stairs)
    
    if config.augmentation:
        apply_augmentation(doc, methods=['rotate', 'scale', 'layer_variation'])
    
    doc.saveas(output_path)
    return build_annotation(walls, doors, windows, stairs, dimensions)
```

### 6.3 数据分层策略

| 数据层级 | 参考1论文 | BAA对应 | 规模 | 用途 |
|---------|---------|--------|------|------|
| **主训练集** | FER-2013 (35,887张) | 合成图纸 | 500-1000张 | 模型训练 |
| **验证集** | CK+ (精确标注) | 合成+真实 | 50-100张合成 + 2-3张真实 | 模型验证+调参 |
| **辅助集** | JAFFE (文化差异) | 地方标准图纸变体 | 20-50张 | 泛化能力测试 |
| **反馈集** | AffectNet (40万张) | 用户真实图纸 | 持续积累 | 数据飞轮 |

---

## 7. 现有代码复用分析

### 7.1 可直接复用的代码

| 文件 | 功能 | 复用方式 |
|------|------|---------|
| `dxf_editor.py` | DXF解析、图层操作、实体编辑 | Step 1的直接实现 |
| `dwg_extractor.py` | DWG二进制提取+LibreDWG转换 | Step 1的DWG入口 |
| `libredwg-web (Node.js WASM)` | DWG→DXF转换 | Step 1的DWG转换引擎 |

### 7.2 需要新增的代码

| 模块 | 估算工作量 | 参考来源 |
|------|-----------|---------|
| Step 2: 图元识别模型 | 3-5天 | 参考1论文4.3节 |
| Step 2: 注意力模块 | 1天 | 参考1论文4.3.3节 |
| Step 2: LoRA微调脚本 | 1天 | 论文#8 |
| Step 3: Whoosh全文检索 | 1天 | — |
| Step 3: Qwen2-1.5B集成 | 1天 | — |
| 合成数据生成工具 | 2-3天 | 参考1论文4.1.2节 |
| 数据增强管线 | 1天 | 参考1论文4.1.2节 |
| 训练脚本 | 2天 | 参考1论文4.4节 |

**总新增代码工作量：12-15天（一人完成）**

---

## 8. 技术风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 合成图纸与真实图纸差距大 | 🟡 中 | 图元识别准确率低 | 3-5张真实图纸LoRA微调 |
| DXF渲染栅格化后信息丢失 | 🟢 低 | 检测精度下降 | 直接使用矢量特征而非栅格化 |
| 训练数据不足（<500张） | 🟡 中 | 模型欠拟合 | 数据增强可扩展5-10倍 |
| YOLOv8+Attention推理慢 | 🟢 低 | 处理时间>10秒 | 先CPU部署，推理优化在P1阶段 |
| Qwen2-1.5B本地部署资源不足 | 🟢 低 | LLM辅助不可用 | 退化为纯手动写JSON |

---

## 9. 交付物清单

| 交付物 | 格式 | 对应章节 | 截止时间 |
|--------|------|---------|---------|
| `drawing_parser.py` | Python | Step 1解析入口 | 第1周 |
| `primitive_model.py` | Python (PyTorch) | Step 2模型定义 | 第2周 |
| `lora_finetune.py` | Python | 4.6节LoRA微调 | 第2周 |
| `spec_retriever.py` | Python (Whoosh) | Step 3规范检索 | 第2周 |
| `llm_spec_helper.py` | Python (Ollama) | Step 3 LLM辅助 | 第2周 |
| `synthetic_generator.py` | Python | 6.2节合成数据 | 第1周 |
| `train_pipeline.py` | Python | 4.5节训练配置 | 第2周 |
| 模型权重 (pth) | 二进制 | 训练产出 | 第3周 |
| 结构化图纸JSON Schema | JSON Schema | Step 5输出规范 | 第1周 |
| 测试报告 | Markdown | DD-7测试方案 | 第3周 |

---

*编制：司军（AI业务助理）*
*日期：2026-06-09（修订版）*
*参考1论文《基于深度学习的人脸表情识别研究》第四章框架迁移*
*新增LoRA微调(4.6节) + RAG规范检索(第5章)，对应决策DD-02/DD-07/DD-11*
