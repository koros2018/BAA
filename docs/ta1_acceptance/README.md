# T-A1 止损感知路线 · 验收证据链

> 验收日期：2026-10-20（阶段 A/B 收口核查）
> 引擎版本：v2.5.80-stable（383207b）
> 结论：三项验收标准全部达标

## 验收标准 1：生产主干无任何光栅/视觉依赖

**grep 依赖清单与 import 链核查（2026-10-20 实测）**：

1. `requirements.txt`：grep `yolo|ultralytics|torch|tensorflow|keras|paddle|opencv|cv2` **零命中**——生产依赖清单无任何光栅/视觉库。
2. import 链全延迟导入，无模块级视觉依赖：
   - `src/api/baa_api.py` L476/L637：`from src.baa_engine.yolo_integrator import YOLODetectionIntegrator` 均在函数体内，且 L635 受 `if use_yolo and VISION_ENABLED` 双守卫；
   - `src/baa_engine/semantic_analyzer/main.py` L966/L972：`_yolo_enhance/_merge_yolo_results` 均为函数内延迟导入；
   - `src/baa_engine/semantic_analyzer/enhancement.py` L15-23：`_yolo_enhance_impl` 为 **P84 永久空返回 stub**（mAP≈0 方案确认不可行，直接 `return []`），引擎主干即使触达也不产生视觉调用；
   - `src/baa_engine/yolo_integrator.py` L144：`from ultralytics import YOLO` 为函数内延迟导入，仅显式调用时加载。
3. 全仓 `import.*yolo|torch|paddle|cv2` 顶层（模块级）import 仅 1 处：`src/tools/p111_train_yolo.py` L15（YOLO 训练研究脚本，非生产调用链）。

## 验收标准 2：关闭视觉后存量测试全部通过、无新增 FAIL

- 开关：`src/api/api_globals.py` L85 `VISION_ENABLED = os.getenv("BAA_VISION_ENABLED", "false")...`——**默认 false**，主干为矢量原生解析。
- 启动校验：`baa_api.py` L303-305 启用时打印警告横幅；L472-473 禁用态在健康检查中明示。
- 回归证据：`src/tests/test_api.py` L46-52 断言 `VISION_ENABLED is False`（默认关闭守卫测试）；当前全量回归 **2505 passed / 0 failed / 14 skipped**（2026-10-20，T-B6 验收口径），覆盖并超越 roadmap 制定时点的 2224+ 存量基线。

## 验收标准 3：研究模块与主干物理隔离，主干运行时不被加载

- YOLO/分割研究链路全部位于 `src/tools/`（`p111_train_yolo.py`、`p111_prepare_data.py`、`p111_data_quality.py`、`auto_annotate_real.py`、`annotate_ui.py`、`visualize_annotations.py`），仅独立脚本入口运行，无生产模块引用。
- grep `from src.tools|import src.tools|from ..tools` 全仓：生产目录（`src/baa_engine/`、`src/api/`）**零命中**；仅 `src/tools/` 内部互引（recall_metrics ← t3_acceptance）。
- 消防符号 spot：无任何生产代码路径（全仓 grep 仅 docs 提及）；其载体（YOLO 训练/标注工具）与主干物理隔离如上。
- 主干运行时（uvicorn 启动 → /review 链路）不加载任何 tools 模块与 ultralytics。

## 备注

- roadmap 制定时的 T-A1 三框当时未勾选，本收口为**实测补验**（非回填推断）：全部结论基于 2026-10-20 对 v2.5.80-stable 代码树的 grep/import 链核查与全量回归结果。
