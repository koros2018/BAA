# D3-T1 报告模板系统方案

> **来源**：`docs/roadmap-phase-d-execution-plan.md` 第 3 节 D3-T1  
> **Roadmap 验收**：交付物包带版本号 + 报告可按标准集切换模板配色  
> **写作日期**：2026-10-27  
> **前置**：T-C5（报告生成器已交付）、D2-T3（export_bundle manifest 已有 report_schema_version）  
> **本方案范围**：D3-T1（模板系统：ReportTemplate + TemplateRegistry + 配色注入）

---

## 1. 现状分析

### 1.1 代码库现状
- `src/baa_engine/report_generator/main.py`：`ReviewReport` 类，硬编码配色 `C_PRIMARY`/`C_SECONDARY`
- `src/baa_engine/report_generator/components.py`：`build_styles()` 无参数，固定使用全局常量
- `docs/tb5_acceptance/`：T-C5 报告生成器已交付，PDF 样式固定蓝色系
- **无模板系统**：无法切换配色/章节顺序/页脚文案

### 1.2 现有接口盘点
| 接口 | 方法 | 产出 | 状态 |
|------|------|------|------|
| `/reviews/{id}/report` | GET | PDF 报告（硬编码模板） | ✅ 已交付 |
| `GET /api/v1/templates` | GET | 模板列表（配色/章节/文案） | ❌ 待实现 |
| `POST /api/v1/templates` | POST | 注册自定义模板 | ❌ 待实现 |

---

## 2. 改造目标与验收标准

### 2.1 Roadmap DoD（原文）
- [ ] 新增 `src/baa_engine/report_generator/template.py`：`ReportTemplate` dataclass + `TemplateRegistry`（内置 + 企业自定义）
- [ ] 报告生成器支持 `template_code` 参数，注入模板配色 + 章节顺序
- [ ] 前端报告页下拉展示可用模板，预览实时切换
- [ ] 前端报告页支持切换标准集 → 触发不同模板

### 2.2 本方案验收标准
| 验收项 | 标准 |
|--------|------|
| ReportTemplate | dataclass，code/name/description/primary_color/accent_color/title/sections/footer_text/logo_path |
| TemplateRegistry | 单例注册表，`register()`/`get()`/`all()` 方法，已知 code 回退 national |
| ReviewReport | 接受 `template_code="national"`，配色/章节按模板切换 |
| GET /api/v1/templates | 返回全部已注册模板（public read） |
| 测试 | `test_report_template.py` 4 用例全过 |

---

## 3. 改造范围（分阶段）

### 3.1 阶段 A：template.py（0.5 天）

**目标**：定义模板数据模型 + 注册表。

**改动**：新建 `src/baa_engine/report_generator/template.py`：
```python
@dataclass
class ReportTemplate:
    code: str
    name: str
    description: str
    primary_color: str = "#1a365d"
    accent_color: str = "#2b6cb0"
    title: str = "审查报告"
    sections: List[str] = field(default_factory=lambda: ["cover", "summary", "violations", "score"])
    footer_text: str = "BAA 智能审查平台"
    logo_path: Optional[str] = None


class TemplateRegistry:
    """单例注册表。"""
    def register(self, tpl: ReportTemplate) -> None
    def get(self, code: str) -> ReportTemplate  # 未知 code 回退 national
    def all(self) -> List[ReportTemplate]
    def load_custom_from_dir(self, directory: str) -> int  # JSON 文件加载
```

内置模板：
- `national`：国标审查模板（深蓝 #1a365d）
- `local`：地标审查模板（棕黄 #744210）

**风险**：低（新建文件，不破坏现有流程）

### 3.2 阶段 B：build_styles() 注入配色（0.5 天）

**目标**：`build_styles()` 接受 primary/secondary hex，覆盖默认配色。

**改动**：
- `components.py`：`build_styles(primary_hex=None, secondary_hex=None)`
- `main.py`：`ReviewReport.generate()` 读取 template_code，调 `build_styles(template.primary_color, ...)`

**风险**：中（修改 existing 函数签名，向后兼容）

### 3.3 阶段 C：API 端点（0.5 天）

**目标**：`GET /api/v1/templates` 返回模板列表。

**改动**：`admin_routes.py` 新增端点（无需认证，公开只读）。

**风险**：低

### 3.4 阶段 D：测试（0.5 天）

**目标**：4 个单测覆盖模板注册、单例 reset、API 端点。

---

## 4. 执行 Checklist
- [ ] `template.py`（ReportTemplate + TemplateRegistry + 内置模板）
- [ ] `components.py` build_styles() 注入配色参数
- [ ] `main.py` ReviewReport 接受 template_code
- [ ] `admin_routes.py` GET /api/v1/templates
- [ ] `test_report_template.py`（4 用例）
- [ ] 全量回归通过
