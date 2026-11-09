# 真实图纸目录空模板排查：A1 等 7 个 DXF 是 ezdxf 空模板（2026-11-10）

> **背景**：排查 `data/drawings/real/` 下真实建筑图纸（`A1云计算中心平面图0405_t3.dxf`、
> `A1IDC及通信机楼结构平面图20161227z.dxf`）解析失败（prims=0）的原因。
> 结论：**这些文件本身是 ezdxf 生成的空模板（0 实体），解析失败是正确行为，不是代码 bug。**
>
> 口径：临时脚本用完即删；本文件仅记录结论。

---

## 1. 排查过程

### 1.1 文件特征

`data/drawings/real/` 下有 **7 个 15267 字节**的 DXF 文件，大小完全相同：

| 文件 | 大小 | ENTITIES 段 | LINE 实体 |
|---|---|---|---|
| `2.1电气170825-报审.dxf` | 15267 | 有 | 0 |
| `6.火灾自动报警_（报审）_t3.dxf` | 15267 | 有 | 0 |
| `9.气体灭火（唯美图框）_t3.dxf` | 15267 | 有 | 0 |
| `A1IDC及通信机楼结构平面图20161227z.dxf` | 15267 | 有 | 0 |
| `A1云计算中心_水消防2017.03.31_t3.dxf` | 15267 | 有 | 0 |
| `A1云计算中心平面图0405_t3.dxf` | 15267 | 有 | 0 |
| `东莞通-设备-外部参照（不打印）.dxf` | 15267 | 有 | 0 |

### 1.2 ezdxf 直接读取验证

```python
import ezdxf
doc = ezdxf.readfile('data/drawings/real/A1云计算中心平面图0405_t3.dxf')
msp = doc.modelspace()
print('entities:', len(list(msp)))   # → 0
print('layers:', [l.dxf.name for l in doc.layers])  # → ['0', 'Defpoints']
```

- modelspace 实体数：**0**
- 图层：仅默认 `0`、`Defpoints`
- `$ACADVER` = `AC1024`，`$LASTSAVEDBY` = `ezdxf`，`$EXTMIN`/`$EXTMAX` = ±1e20（无实体）

**结论**：这些文件是 ezdxf 生成的**空模板**（`ezdxf.new()` 后未添加任何实体即保存）。

### 1.3 解析器验证

用 `DrawingParser.parse` 实际解析：

| 文件 | prims | error |
|---|---|---|
| `A1云计算中心平面图0405_t3.dxf` | 0 | None |
| `4.通风BS170826.dxf`（45417B，非空模板） | 9 | None |
| `Demo - Hotel (Template F1-F2-F3).dxf`（cype 模板） | 169 | None |

- 空模板 → 0 prims（正确，文件无图元）
- 非空模板 → 正常解析（9 / 169 prims）
- cype 酒店模板有实际图层（PARTITION/DOOR/EXTERNAL_WALL/WINDOW/COLUMN/FLOOR_SLAB）

### 1.4 测试影响

`test_p121_drawing_classifier.py` 对这些文件只测**文件名分类**（`classify_drawing`），
不依赖文件内容；L625-631 明确接受"0 实体且文件小"为损坏标记。相关测试 54 passed。

---

## 2. 结论

1. **A1 云计算中心平面图等 7 个 15267 字节 DXF 是 ezdxf 空模板**（0 实体，仅默认图层）。
2. 解析失败（prims=0）是**正确行为**——文件本身没有图元，不是代码 bug。
3. 这些文件被 `.gitignore` 排除（`git check-ignore` 返回路径），是**本地测试数据**，
   不进入仓库，不影响 CI。
4. `4.通风BS170826.dxf`（9 实体）和 cype 模板（169 实体）是有效图纸，解析器工作正常。

**建议**：若需真实建筑图纸测试数据，应替换这些空模板为实际图纸内容；
当前无需修改解析器代码。
