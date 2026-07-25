# BAA 版本记录

## v2.5.15-stable (2026-07-24) — 当前
- HEAD: aa5179b
- P70 全覆盖: 340/340 实体类型, 1198/1198 refs (100%)
- P70 误报修复: FAIL 从 8659 (14.9%) → 545 (1.1%), 减少 93.7%
- 修复: EXIST-052/083/093 系统性误报 (requires_global_context)
- 修复: _classify_by_geometry 两处未定义变量

## v2.5.14-stable (2026-07-21) — 回退版
- HEAD: bed126e
- P58-P62 功能完整
- P69 PDF 后端已完成
- 实体覆盖: 289/345 (P70 之前状态)

## 回退操作
```bash
git checkout v2.5.14-stable   # 回退到上一稳定版
git checkout v2.5.15-stable   # 切回当前最新稳定版
```
