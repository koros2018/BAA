"""
图纸渲染端点（SVG输出）
在现有 baas_api.py 文件末尾追加以下代码（位于 `get_order` 函数之后，静态文件服务之前）
"""

# ── 图纸渲染 ──────────────────────────────────────────────
# 将以下代码插入到 `get_order` 的 return 之后、静态文件挂载之前

@app.get("/render/{file_id}")
async def render_drawing(
    file_id: str,  # 操作
    request: Request = None,  # 赋值
    api_key: str = Depends(verify_api_key),  # 赋值
):  # 闭合
    """将 DXF/DWG 图纸渲染为 SVG 供前端展示"""
    file_path = get_file_path(file_id)  # 赋值
    if not file_path:  # 条件判断
        raise HTTPException(status_code=404, detail={"status": "error", "message": "文件不存在"})  # 抛出异常

    import ezdxf
    from io import StringIO

    try:  # 尝试
        doc = ezdxf.readfile(str(file_path))  # 赋值
        msp = doc.modelspace()  # 赋值
    except Exception:  # 捕获异常
        raise HTTPException(status_code=400, detail={"status": "error", "message": "无法解析图纸文件"})  # 抛出异常

    # 计算边界
    all_x, all_y = [], []  # 赋值
    for entity in msp:  # 循环
        try:  # 尝试
            if entity.dxftype() == "LINE":  # 条件判断
                s, e = entity.dxf.start, entity.dxf.end  # 赋值
                all_x.extend([s[0], e[0]])  # 调用
                all_y.extend([s[1], e[1]])  # 调用
            elif entity.dxftype() == "LWPOLYLINE":  # 分支
                pts = [(v[0], v[1]) for v in entity.get_points()]  # 赋值
                all_x.extend(p[0] for p in pts)  # 调用
                all_y.extend(p[1] for p in pts)  # 调用
            elif entity.dxftype() == "CIRCLE":  # 分支
                cx, cy = entity.dxf.center[:2]  # 赋值
                r = entity.dxf.radius  # 赋值
                all_x.extend([cx - r, cx + r])  # 调用
                all_y.extend([cy - r, cy + r])  # 调用
            elif entity.dxftype() in ("TEXT", "MTEXT"):  # 分支
                ins = entity.dxf.insert[:2]  # 赋值
                all_x.append(ins[0])  # 调用
                all_y.append(ins[1])  # 调用
        except Exception:  # 捕获异常
            continue  # 继续循环

    if not all_x:  # 条件判断
        return {"status": "error", "message": "图纸无有效图元"}  # 返回

    margin = 5.0  # 赋值
    x_min, x_max = min(all_x) - margin, max(all_x) + margin  # 解包
    y_min, y_max = min(all_y) - margin, max(all_y) + margin  # 解包
    w, h = x_max - x_min, y_max - y_min  # 赋值

    # SVG 尺寸
    svg_w = min(max(w * 0.5, 400), 1200)  # 赋值
    svg_h = min(max(h * 0.5, 300), 800)  # 赋值

    buf = StringIO()  # 赋值
    buf.write(f'<svg xmlns="http://www.w3.org/2000/svg" '  # 调用
              f'viewBox="{x_min} {-y_max} {w} {h}" '  # 操作
              f'width="{svg_w}" height="{svg_h}" '  # 操作
              f'style="background:#fff">\n')

    max_entities = 2000  # 赋值
    drawn = 0  # 赋值

    for entity in msp:  # 循环
        if drawn >= max_entities:  # 条件判断
            break  # 跳出循环
        dxftype = entity.dxftype()  # 赋值
        try:  # 尝试
            if dxftype == "LINE":  # 条件判断
                s, e = entity.dxf.start, entity.dxf.end  # 赋值
                buf.write(f'<line x1="{s[0]:.2f}" y1="{-s[1]:.2f}" '  # 调用
                          f'x2="{e[0]:.2f}" y2="{-e[1]:.2f}" '  # 操作
                          f'stroke="#333" stroke-width="0.5" />\n')
                drawn += 1  # 赋值
            elif dxftype == "LWPOLYLINE":  # 分支
                pts = [(v[0], -v[1]) for v in entity.get_points()]  # 赋值
                d = "M" + " L".join(f"{p[0]:.2f},{p[1]:.2f}" for p in pts)  # 赋值
                buf.write(f'<path d="{d}" fill="none" stroke="#333" stroke-width="0.5" />\n')
                drawn += 1  # 赋值
            elif dxftype == "CIRCLE":  # 分支
                cx, cy = entity.dxf.center[:2]  # 赋值
                r = entity.dxf.radius  # 赋值
                buf.write(f'<circle cx="{cx:.2f}" cy="{-cy:.2f}" r="{r:.2f}" '  # 调用
                          f'fill="none" stroke="#333" stroke-width="0.5" />\n')
                drawn += 1  # 赋值
            elif dxftype in ("TEXT", "MTEXT"):  # 分支
                ins = entity.dxf.insert[:2]  # 赋值
                txt = entity.dxf.text if hasattr(entity.dxf, 'text') else ''  # 赋值
                h = entity.dxf.height if hasattr(entity.dxf, 'height') else 2.5  # 赋值
                buf.write(f'<text x="{ins[0]:.2f}" y="{-ins[1]:.2f}" '  # 调用
                          f'font-size="{h}" fill="#666">{txt[:30]}</text>\n')
                drawn += 1  # 赋值
        except Exception:  # 捕获异常
            continue  # 继续循环

    buf.write('</svg>')  # 调用
    svg_content = buf.getvalue()  # 赋值

    return Response(content=svg_content, media_type="image/svg+xml")  # 返回
