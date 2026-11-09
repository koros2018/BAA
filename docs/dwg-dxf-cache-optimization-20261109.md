# DWG→DXF 磁盘缓存优化（2026-11-09）

> **背景**：Heavy DWG（9.9MB）解析约 46 秒，主因是 `ezdwg.read()` +
> `export_dxf()` 每次 analyze 都重新转换。同一 DWG 多次解析时重复耗时。
> 本次新增磁盘缓存，命中时跳过转换，热解析降至 8.84s（5.2x）。
>
> 口径：`data/files/*.dwg`。临时脚本用完即删。

---

## 1. 性能定位

| 阶段 | 耗时 | 说明 |
|------|------|------|
| `ezdwg.read()` | 主要 | 解析 DWG 二进制（第三方库，无法优化） |
| `dwg_doc.export_dxf()` | 次要 | 导出 DXF |
| `ezdxf.readfile()` | 约 2s | 读取转换后的 DXF |

9.9MB DWG（46201 图元）冷解析 46.33s。

**问题**：`DrawingParser._parse_cache` 是**实例内**缓存，每次 analyze 创建新
实例则重新转换。`_parse_dwg` 内部无跨实例缓存。

---

## 2. 缓存设计

### 2.1 缓存键

```python
def _dwg_cache_key(path: Path) -> str:
    st = path.stat()
    return f"{path.resolve()}_{st.st_mtime_ns}_{st.st_size}"
```

用 `mtime_ns + size` 而非 hash：避免对大文件（9.9MB）做 SHA256 的成本。
`mtime_ns` 纳秒精度足够检测文件变更。

### 2.2 缓存位置

`tempfile.gettempdir() / "baa_dwg_dxf_cache"`，缓存文件按 MD5(键)[:16] 命名。

- 系统临时目录：重启清空（缓存是优化非依赖，可接受）
- 原子写入：先写 `.tmp` 再 `replace()`，避免并发读半成品

### 2.3 命中验证

缓存命中时仍需验证非零图层（缓存文件应保留图层信息），无有效图层则降级
到下一级兜底。这保证缓存文件与首次转换的验证逻辑一致。

### 2.4 失效

- 缓存损坏（`ezdxf.readfile` 失败）→ 自动删除并重新转换
- mtime/size 变化 → 缓存键变化，自动失效

---

## 3. 性能验证（9.9MB DWG，46201 图元）

| 解析 | 耗时 | 说明 |
|------|------|------|
| 冷（首次） | 46.33s | 转换 + 写缓存 |
| 热（命中） | 8.84s | 仅 `ezdxf.readfile(cached)` |
| **提升** | **5.2x** | primitives 完全一致（46201） |

小 DWG（522KB）：
- 冷：3.62s → 热：2.18s（1.7x，`ezdxf.readfile` 占大头）

---

## 4. 代码改动

文件：[dwg_convert.py](file:///d:/OpenClawData/BAA/src/baa_engine/parsers/dwg_convert.py)

| 位置 | 变更 |
|------|------|
| L26-74 | 新增 `_DWG_CACHE_DIR` + `_dwg_cache_key` / `_dwg_cache_path` / `_try_dwg_cache` / `_write_dwg_cache` |
| L857-880 | `_try_ezdwg_direct`（第 0 级主路径）：缓存命中跳过转换 + 验证图层 |
| L908-912 | `_try_ezdwg_direct` 转换成功后写缓存（先写缓存再删临时文件） |
| L267-288 | `_try_ezdwg_export_dxf`（第 1 级兜底）：同样加缓存检查 |

---

## 5. 测试

- 全量测试：3106 passed, 28 skipped, 14 deselected（无回归）
- 冷/热对比：大 DWG 5.2x，小 DWG 1.7x，primitives 一致

---

## 6. 待观察项

- **`_try_ezdwg_direct` 与 `_try_ezdwg_export_dxf` 都加缓存**：两者缓存键相同，
  若第 0 级失败降级到第 1 级，第 1 级会命中第 0 级写入的缓存（若第 0 级
  转换成功但图层验证失败则未写缓存，第 1 级重新转换）。逻辑正确。
- **缓存目录无自动清理**：长期运行可能积累大量 DXF 缓存文件。若需控制，
  可加 LRU 清理（按 mtime 删除最旧）。当前临时目录重启清空，暂不处理。
