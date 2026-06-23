"""
图纸渲染端点（SVG输出）
在现有 baas_api.py 文件末尾追加以下代码（位于 `get_order` 函数之后，静态文件服务之前）
"""

# ── 图纸渲染 ──────────────────────────────────────────────
# 将以下代码插入到 `get_order` 的 return 之后、静态文件挂载之前

@app.get("/render/{file_id}")
async def render_drawing(
    file_id: str,
    request: Request = None,
    api_key: str = Depends(verify_api_key),
):
    """将 DXF/DWG 图纸渲染为 SVG 供前端展示"""
    file_path = get_file_path(file_id)
    if not file_path:
        raise HTTPException(status_code=404, detail={"status": "error", "message": "文件不存在"})

    import ezdxf
    from io import StringIO

    try:
        doc = ezdxf.readfile(str(file_path))
        msp = doc.modelspace()
    except Exception:
        raise HTTPException(status_code=400, detail={"status": "error", "message": "无法解析图纸文件"})

    # 计算边界
    all_x, all_y = [], []
    for entity in msp:
        try:
            if entity.dxftype() == "LINE":
                s, e = entity.dxf.start, entity.dxf.end
                all_x.extend([s[0], e[0]])
                all_y.extend([s[1], e[1]])
            elif entity.dxftype() == "LWPOLYLINE":
                pts = [(v[0], v[1]) for v in entity.get_points()]
                all_x.extend(p[0] for p in pts)
                all_y.extend(p[1] for p in pts)
            elif entity.dxftype() == "CIRCLE":
                cx, cy = entity.dxf.center[:2]
                r = entity.dxf.radius
                all_x.extend([cx - r, cx + r])
                all_y.extend([cy - r, cy + r])
            elif entity.dxftype() in ("TEXT", "MTEXT"):
                ins = entity.dxf.insert[:2]
                all_x.append(ins[0])
                all_y.append(ins[1])
        except Exception:
            continue

    if not all_x:
        return {"status": "error", "message": "图纸无有效图元"}

    margin = 5.0
    x_min, x_max = min(all_x) - margin, max(all_x) + margin
    y_min, y_max = min(all_y) - margin, max(all_y) + margin
    w, h = x_max - x_min, y_max - y_min

    # SVG 尺寸
    svg_w = min(max(w * 0.5, 400), 1200)
    svg_h = min(max(h * 0.5, 300), 800)

    buf = StringIO()
    buf.write(f'<svg xmlns="http://www.w3.org/2000/svg" '
              f'viewBox="{x_min} {-y_max} {w} {h}" '
              f'width="{svg_w}" height="{svg_h}" '
              f'style="background:#fff">\n')

    max_entities = 2000
    drawn = 0

    for entity in msp:
        if drawn >= max_entities:
            break
        dxftype = entity.dxftype()
        try:
            if dxftype == "LINE":
                s, e = entity.dxf.start, entity.dxf.end
                buf.write(f'<line x1="{s[0]:.2f}" y1="{-s[1]:.2f}" '
                          f'x2="{e[0]:.2f}" y2="{-e[1]:.2f}" '
                          f'stroke="#333" stroke-width="0.5" />\n')
                drawn += 1
            elif dxftype == "LWPOLYLINE":
                pts = [(v[0], -v[1]) for v in entity.get_points()]
                d = "M" + " L".join(f"{p[0]:.2f},{p[1]:.2f}" for p in pts)
                buf.write(f'<path d="{d}" fill="none" stroke="#333" stroke-width="0.5" />\n')
                drawn += 1
            elif dxftype == "CIRCLE":
                cx, cy = entity.dxf.center[:2]
                r = entity.dxf.radius
                buf.write(f'<circle cx="{cx:.2f}" cy="{-cy:.2f}" r="{r:.2f}" '
                          f'fill="none" stroke="#333" stroke-width="0.5" />\n')
                drawn += 1
            elif dxftype in ("TEXT", "MTEXT"):
                ins = entity.dxf.insert[:2]
                txt = entity.dxf.text if hasattr(entity.dxf, 'text') else ''
                h = entity.dxf.height if hasattr(entity.dxf, 'height') else 2.5
                buf.write(f'<text x="{ins[0]:.2f}" y="{-ins[1]:.2f}" '
                          f'font-size="{h}" fill="#666">{txt[:30]}</text>\n')
                drawn += 1
        except Exception:
            continue

    buf.write('</svg>')
    svg_content = buf.getvalue()

    return Response(content=svg_content, media_type="image/svg+xml")