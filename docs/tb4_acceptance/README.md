# T-B4 报告产品化证据链（三格式导出 · 审图视角验收）

> 关联：Roadmap v4 T-B4（G3 / B4）。基线 T-B3（62f21dc）之上。验收：审图机构视角可用无空白章节 + 三格式内容一致、条款索引可跳转。

## 一、交付物

| 模块 | 文件 | 内容 |
|---|---|---|
| PDF 补页 | `src/baa_engine/report_generator/product_pages.py` | 条款索引页（条款→标题/规范/最高严重度/次数）/ 审查结论页（三档判定 + 严重度分布 + 整改路径）/ 签署归档页（项目信息 + 编制/审核/批准签栏 + 免责声明），由 `main.generate()` 编排追加 |
| HTML 导出 | `src/api/review/html_report.py` | 自包含单文件（内联 CSS），与 PDF 同结构，条款索引锚点 `#clause-<id>` 跳转至明细行 |
| Excel 导出 | `src/api/review/xlsx_report.py` | openpyxl 三 sheet（汇总 kv / 条款索引 / 违规明细冻结首行），严重度色块 |
| 路由挂接 | `src/api/review/review_routes.py` | `/review/export?format=html\|xlsx` 两个新分支（原有 json/csv 不变） |
| 依赖 | `requirements.txt` | `openpyxl>=3.1.0`（reportlab 已有） |

## 二、过程真实缺陷修复

1. **签栏单元格嵌套列表 → `'str' has no attribute 'wrapOn'`**：sign 表构造把角色名包成 `["编制（审查引擎）"]` 列表，reportlab Table 将 list 单元格按 Flowable 组处理、对其中 str 调 `wrapOn` 即崩。str 藏在 Table 单元格内层，顶层 buf 扫描不可见（trace 两轮才定位）。
2. **表格 str 单元格缺 FONTNAME**：默认 Helvetica 画中文在 build 期有编码风险，4 个新表统一补 `("FONTNAME", ..., "WQY")`。
3. **build_doc 空 bytes 存量隐患（/review/pdf 潜在空响应）**：`output_path` 模式返回 `b""`，而两个 API 调用方（render_routes `/review/pdf`、review_routes 审查报告）都直接消费返回字节。修正：output_path 模式落盘后读回返回字节；无路径模式由硬编码 `/tmp/baa_report.pdf` 改为 `tempfile.mkstemp` 唯一临时文件（消灭 /tmp 依赖与并发覆盖）。修复后 output_path 模式 PDF 首字节 `%PDF` 断言通过。
4. **三格式严重度枚举断层**：结论页/汇总初版用 `high/medium/low`，而引擎权威枚举（`atomic_functions.Severity`）为 `critical/major/minor`（violations.py 展示层同源）→ 三格式统一为 critical/major/minor，PDF 列头「critical（强制）/major（较大）/minor（一般）」。

## 三、验收结果

| 验收条款 | 结果 | 证据 |
|---|---|---|
| 审图机构视角可用，无空白章节 | **通过** | `sample_report.pdf`（10 页，pypdf 逐页文本提取 0 空白页）；章节序：封面→审查评分(3)→审查摘要(4)→整改优先级(5)→修正建议(6)→条款索引/违规详情(8)→审查结论(9)→签署与归档(10) |
| 三格式内容一致、条款索引可跳转 | **通过** | 同一 details 源：PDF/HTML/XLSX 条款集合一致 `{6.1.2, 5.5.18, 8.3.1, 6.2.5, 7.1.3}`；HTML 锚点 `href="#clause-<id>"` ↔ 明细行 `id="clause-<id>-<i>"` |
| 测试 | 6/6 | `test_report_productization.py`（PDF 新页+空明细 / HTML 结构与锚点 / XLSX sheet / 路由契约 / 三格式一致性） |
| 全量回归 | **2470 passed / 0 failed**（基线 2464 + 新增 6） | 含 build_doc 改动后 `/review/pdf` 相关路由测试 |

## 四、产物清单（本目录）

- `sample_report.pdf` / `sample_report.html` / `sample_report.xlsx` — 同一数据源三格式产物（字段结构与引擎 details 对齐的构造样本；审查层数据真实性由 T-A4/T-B1/T-B2/T-B3 证据链背书，本任务验收对象为报告层结构与一致性）

## 五、复现

```bash
python -m pytest src/tests/test_report_productization.py -q   # 6 passed
python -m pytest src/tests -q                                  # 2470 passed / 0 failed
```
