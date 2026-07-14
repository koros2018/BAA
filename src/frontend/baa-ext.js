// BAA P56+P57: 反向重构 + 原子函数库
// 从 index.html 拆分出来，减小主文件体积

// ── P56 反向重构 ──

async function generateReverse() {
    const result = document.getElementById('reverse-result');
    const err = document.getElementById('reverse-error');
    if (!result) return;
    const constraints = document.getElementById('reverse-constraints');
    const validation = document.getElementById('reverse-validation');
    const dxfPre = document.getElementById('reverse-dxf');
    result.classList.add('hidden');
    err.classList.add('hidden');

    const body = {
        room_type: document.getElementById('reverse-room-type')?.value || 'office',
        width_mm: parseInt(document.getElementById('reverse-width')?.value) || 5000,
        height_mm: parseInt(document.getElementById('reverse-height')?.value) || 4000,
        door_width_mm: parseInt(document.getElementById('reverse-door-width')?.value) || null,
    };

    try {
        const resp = await fetch('/api/v1/reverse', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + (getApiKey() || '')},
            body: JSON.stringify(body),
        });
        const data = await resp.json();
        if (data.status !== 'ok') {
            err.textContent = '错误: ' + JSON.stringify(data);
            err.classList.remove('hidden');
            return;
        }

        const c = data.constraints;
        constraints.innerHTML = '<table class="w-full text-sm">' +
            '<tr><td class="py-1 text-gray-500">最小宽度</td><td class="py-1">' + c.min_width_mm + ' mm</td></tr>' +
            '<tr><td class="py-1 text-gray-500">最小高度</td><td class="py-1">' + c.min_height_mm + ' mm</td></tr>' +
            '<tr><td class="py-1 text-gray-500">最小门宽</td><td class="py-1">' + c.min_door_width_mm + ' mm</td></tr>' +
            '<tr><td class="py-1 text-gray-500">面积</td><td class="py-1">' + c.min_area_m2.toFixed(1) + ' m²</td></tr>' +
            (c.notes.length ? '<tr><td class="py-1 text-gray-500">规范约束</td><td class="py-1">' + c.notes.join('<br>') + '</td></tr>' : '') +
            '</table>';

        // 渲染单房间 SVG 可视化
        const svgContainer = document.getElementById('reverse-svg');
        if (svgContainer && data.validation) {
            const singleLayout = {
                rooms: [{
                    type: body.room_type,
                    x: 0, y: 0,
                    w: body.width_mm,
                    h: body.height_mm
                }],
                corridor: null
            };
            svgContainer.innerHTML = renderLayoutSVG(singleLayout, data.validation);
            window._reverseSVGLayout = singleLayout;
            window._reverseSVGValidation = data.validation;
        }

        // 验证结果
        const v = data.validation || {};
        validation.innerHTML = '<span class="' + (v.all_pass ? 'text-green-600' : 'text-red-600') + '" font-bold>' +
            (v.all_pass ? '✅ 闭环验证通过' : '❌ ' + (v.fail_count || '?') + ' FAIL') +
            '</span>';

        dxfPre.textContent = data.dxf;
        result.classList.remove('hidden');
    } catch(e) {
        err.textContent = '请求失败: ' + e.message;
        err.classList.remove('hidden');
    }
}

function copyReverseDXF() {
    const dxf = document.getElementById('reverse-dxf');
    if (dxf) { navigator.clipboard.writeText(dxf.textContent).then(() => alert('DXF 已复制到剪贴板')); }
}

// ── P57 原子函数库 ──

async function loadFunctions() {
    try {
        const resp = await fetch('/api/v1/functions', {
            headers: {'Authorization': 'Bearer ' + (getApiKey() || '')},
        });
        const data = await resp.json();
        if (data.status !== 'ok') return;

        document.getElementById('func-count').textContent = '共 ' + data.count + ' 个函数';

        const categories = new Set();
        data.functions.forEach(f => categories.add(f.category));
        const filter = document.getElementById('func-category-filter');
        if (filter) {
            categories.forEach(cat => {
                const opt = document.createElement('option');
                opt.value = cat;
                opt.textContent = cat;
                filter.appendChild(opt);
            });
        }

        window._allFuncs = data.functions;
        filterFunctions();
    } catch(e) {
        const el = document.getElementById('func-list');
        if (el) el.innerHTML = '<div class="text-center text-red-500 py-8">加载失败: ' + e.message + '</div>';
    }
}

function filterFunctions() {
    const search = document.getElementById('func-search')?.value.toLowerCase() || '';
    const category = document.getElementById('func-category-filter')?.value || '';
    const funcs = window._allFuncs || [];
    const list = document.getElementById('func-list');
    if (!list) return;

    const filtered = funcs.filter(f => {
        if (category && f.category !== category) return false;
        if (search && !f.func_id.toLowerCase().includes(search) && !f.name.toLowerCase().includes(search)) return false;
        return true;
    });

    list.innerHTML = filtered.map(f => {
        const catColors = {dim: 'blue', dist: 'green', count: 'purple', attr: 'orange', exist: 'red', area: 'teal', evac: 'pink', access: 'indigo'};
        const color = catColors[f.category] || 'gray';
        const fid = f.func_id;
        return '<div class="card p-3 hover:shadow-md transition cursor-pointer" onclick="toggleFuncDetail(&#39;' + fid + '&#39;)">' +
            '<div class="flex items-center justify-between">' +
            '<div class="flex items-center gap-2">' +
            '<span class="text-xs font-mono bg-' + color + '-100 text-' + color + '-700 px-2 py-0.5 rounded">' + fid + '</span>' +
            '<span class="font-medium">' + f.name + '</span>' +
            '</div>' +
            '<span class="text-xs text-gray-400">' + f.clause_id + '</span>' +
            '</div>' +
            '<div class="text-sm text-gray-500 mt-1">' + f.description + '</div>' +
            '<div id="detail-' + fid + '" class="hidden mt-2 pt-2 border-t border-gray-100">' +
            '<div class="grid grid-cols-2 gap-2 text-sm">' +
            '<div><span class="text-gray-500">目标实体:</span> ' + (f.target_entities || []).join(', ') + '</div>' +
            '<div><span class="text-gray-500">运算符:</span> ' + f.operator + '</div>' +
            '<div><span class="text-gray-500">阈值:</span> <input class="input w-24 inline text-sm" value="' + f.threshold + '" id="th-' + fid + '" /></div>' +
            '<div><span class="text-gray-500">单位:</span> <input class="input w-20 inline text-sm" value="' + f.unit + '" id="unit-' + fid + '" /></div>' +
            '</div>' +
            '<button class="btn-primary text-xs mt-2" onclick="event.stopPropagation();updateFunction(&#39;' + fid + '&#39;)">保存修改</button>' +
            '</div>' +
            '</div>';
    }).join('');
}

function toggleFuncDetail(funcId) {
    const el = document.getElementById('detail-' + funcId);
    if (el) el.classList.toggle('hidden');
}

async function updateFunction(funcId) {
    const th = document.getElementById('th-' + funcId);
    const unit = document.getElementById('unit-' + funcId);
    if (!th || !unit) return;
    try {
        const resp = await fetch('/api/v1/functions/' + funcId + '/update', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + (getApiKey() || '')},
            body: JSON.stringify({threshold: parseFloat(th.value), unit: unit.value}),
        });
        const data = await resp.json();
        alert(data.message || '更新成功');
    } catch(e) {
        alert('更新失败: ' + e.message);
    }
}

// ── P58 多房间布局生成 ──

// 反向重构 Tab 切换
function switchRevTab(tab) {
    const singlePanel = document.getElementById('rev-single-panel');
    const multiPanel = document.getElementById('rev-multi-panel');
    const tabSingle = document.getElementById('rev-tab-single');
    const tabMulti = document.getElementById('rev-tab-multi');
    const result = document.getElementById('reverse-result');
    const err = document.getElementById('reverse-error');
    
    if (tab === 'multi') {
        singlePanel.classList.add('hidden');
        multiPanel.classList.remove('hidden');
        tabSingle.classList.remove('bg-white', 'shadow-sm', 'font-medium');
        tabSingle.classList.add('text-gray-600');
        tabMulti.classList.add('bg-white', 'shadow-sm', 'font-medium');
        tabMulti.classList.remove('text-gray-600');
        // 初始化多房间表单
        initMultiRooms();
    } else {
        singlePanel.classList.remove('hidden');
        multiPanel.classList.add('hidden');
        tabSingle.classList.add('bg-white', 'shadow-sm', 'font-medium');
        tabSingle.classList.remove('text-gray-600');
        tabMulti.classList.remove('bg-white', 'shadow-sm', 'font-medium');
        tabMulti.classList.add('text-gray-600');
    }
    // 隐藏旧结果
    result.classList.add('hidden');
    err.classList.add('hidden');
}

// 初始化多房间表单（默认3个房间）
function initMultiRooms() {
    const list = document.getElementById('multi-room-list');
    if (!list || list.children.length > 0) return; // 已初始化
    addMultiRoom('office', 5000, 4000, 900);
    addMultiRoom('equipment', 3000, 3000, 900);
    addMultiRoom('accessible_toilet', 2500, 2500, 900);
}

// 添加一个房间行
function addMultiRoom(type, width, height, doorWidth) {
    const list = document.getElementById('multi-room-list');
    if (!list) return;
    const idx = list.children.length;
    const div = document.createElement('div');
    div.className = 'multi-room-row flex items-center gap-2 mb-2 p-2 border rounded-lg bg-gray-50';
    div.innerHTML = `
        <select class="multi-room-type input text-sm w-28">
            <option value="office" ${type === 'office' ? 'selected' : ''}>办公室</option>
            <option value="stair" ${type === 'stair' ? 'selected' : ''}>楼梯间</option>
            <option value="corridor" ${type === 'corridor' ? 'selected' : ''}>走廊</option>
            <option value="exit" ${type === 'exit' ? 'selected' : ''}>安全出口</option>
            <option value="fire_lobby" ${type === 'fire_lobby' ? 'selected' : ''}>前室</option>
            <option value="equipment" ${type === 'equipment' ? 'selected' : ''}>设备间</option>
            <option value="accessible_toilet" ${type === 'accessible_toilet' ? 'selected' : ''}>无障碍卫生间</option>
        </select>
        <input class="multi-room-width input text-sm w-20" value="${width || 5000}" placeholder="宽" />
        <input class="multi-room-height input text-sm w-20" value="${height || 4000}" placeholder="高" />
        <input class="multi-room-door-width input text-sm w-20" value="${doorWidth || ''}" placeholder="门宽" />
        <span class="text-xs text-gray-400 w-16">mm</span>
        <button class="text-red-500 hover:text-red-700 text-sm" onclick="this.closest('.multi-room-row').remove()">✕</button>
    `;
    list.appendChild(div);
}

async function generateMultiReverse() {
    const result = document.getElementById('reverse-result');
    const err = document.getElementById('reverse-error');
    if (!result) return;
    const layoutDiv = document.getElementById('reverse-layout');
    const dxfPre = document.getElementById('reverse-dxf');
    const validationDiv = document.getElementById('reverse-validation');
    result.classList.add('hidden');
    err.classList.add('hidden');

    // 从页面表单收集房间列表
    const roomRows = document.querySelectorAll('.multi-room-row');
    const rooms = [];
    roomRows.forEach(row => {
        const roomType = row.querySelector('.multi-room-type')?.value || 'office';
        const width = parseInt(row.querySelector('.multi-room-width')?.value) || 5000;
        const height = parseInt(row.querySelector('.multi-room-height')?.value) || 4000;
        const doorWidth = parseInt(row.querySelector('.multi-room-door-width')?.value) || null;
        rooms.push({room_type: roomType, width_mm: width, height_mm: height, door_width_mm: doorWidth});
    });

    // 如果表单不存在，使用默认房间
    if (rooms.length === 0) {
        rooms.push({room_type: 'office', width_mm: 5000, height_mm: 4000});
        rooms.push({room_type: 'stair', width_mm: 3000, height_mm: 5000});
    }

    const body = {
        rooms: rooms,
        validate: true,
    };

    try {
        const resp = await fetch('/api/v1/reverse/multi', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + (getApiKey() || '')},
            body: JSON.stringify(body),
        });
        const data = await resp.json();
        if (data.status !== 'ok') {
            err.textContent = '错误: ' + JSON.stringify(data);
            err.classList.remove('hidden');
            return;
        }

        // 渲染 SVG 可视化布局
        const l = data.layout;
        const svgContainer = document.getElementById('reverse-svg');
        if (svgContainer) {
            svgContainer.innerHTML = renderLayoutSVG(l, data.validation);
            // 全局引用供展开/下载
            window._reverseSVGLayout = l;
            window._reverseSVGValidation = data.validation;
        }

        // 验证结果
        const v = data.validation || {};
        if (validationDiv) {
            validationDiv.innerHTML = '<span class="' + (v.all_pass ? 'text-green-600' : 'text-gray-500') + ' font-bold">' +
                (v.all_pass ? '✅ 闭环验证通过' : '验证未开启') +
                '</span>';
        }

        // DXF 内容
        dxfPre.textContent = data.dxf;
        result.classList.remove('hidden');
    } catch(e) {
        err.textContent = '请求失败: ' + e.message;
        err.classList.remove('hidden');
    }
}

// ── P58 布局可视化 ──

/**
 * 将房间布局渲染为 SVG。
 * 单位转换：mm → px (scale = 0.1px/mm)，带 50px 边距
 */
function renderLayoutSVG(layout, validation) {
    const rooms = layout.rooms || [];
    const corridor = layout.corridor;
    if (!rooms.length && !corridor) return '<div class="text-center text-gray-400 py-8">无布局数据</div>';

    const SCALE = 0.1;  // mm → px
    const MARGIN = 40;  // px

    // 计算包围盒
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    rooms.forEach(r => {
        minX = Math.min(minX, r.x); minY = Math.min(minY, r.y);
        maxX = Math.max(maxX, r.x + r.w); maxY = Math.max(maxY, r.y + r.h);
    });
    if (corridor) {
        // corridor 在 DXF 中位置由引擎生成，这里用估算：在房间之间
        // 简化：取 x=0, y 在上下房间之间
        const ys = rooms.map(r => r.y + r.h).concat(rooms.map(r => r.y));
        const midY = Math.min(...ys);
        minX = Math.min(minX, 0); minY = Math.min(minY, midY - corridor.h);
        maxX = Math.max(maxX, corridor.w);
        maxY = Math.max(maxY, midY);
    }

    const svgW = (maxX - minX) * SCALE + MARGIN * 2;
    const svgH = (maxY - minY) * SCALE + MARGIN * 2;

    const colorMap = {
        office: '#dbeafe', stair: '#bfdbfe', corridor: '#e0f2fe',
        exit: '#bbf7d0', fire_lobby: '#fde68a', equipment: '#fed7aa',
        accessible_toilet: '#ddd6fe', bedroom: '#fce7f3', wc: '#f3e8ff',
        toilet: '#f3e8ff', hallway: '#ecfeff', kitchen: '#fef9c3',
        bathroom: '#e0e7ff'
    };
    const borderMap = {
        office: '#3b82f6', stair: '#2563eb', corridor: '#0891b2',
        exit: '#16a34a', fire_lobby: '#d97706', equipment: '#ea580c',
        accessible_toilet: '#7c3aed', bedroom: '#db2777', wc: '#8b5cf6',
        toilet: '#8b5cf6', hallway: '#06b6d4', kitchen: '#ca8a04',
        bathroom: '#6366f1'
    };

    let svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${svgW} ${svgH}" style="width:100%;height:100%;display:block;background:#fafafa" font-family="system-ui,sans-serif">`;

    // 定义箭头
    svg += `<defs><marker id="arrow-evac" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto"><path d="M0,0 L8,3 L0,6" fill="#ef4444" stroke="#ef4444" stroke-width="0.5"/></marker></defs>`;

    // 绘制房间
    rooms.forEach(r => {
        const x = (r.x - minX) * SCALE + MARGIN;
        const y = (r.y - minY) * SCALE + MARGIN;
        const w = r.w * SCALE;
        const h = r.h * SCALE;
        const fill = colorMap[r.type] || '#e5e7eb';
        const stroke = borderMap[r.type] || '#6b7280';
        svg += `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${fill}" stroke="${stroke}" stroke-width="2" rx="2"/>`;
        // 房间标签
        const label = r.type.charAt(0).toUpperCase() + r.type.slice(1).replace(/_/g, ' ');
        const labelFontSize = Math.max(9, Math.min(14, Math.min(w, h) / 6));
        svg += `<text x="${x + w/2}" y="${y + h/2 - 4}" text-anchor="middle" font-size="${labelFontSize}" font-weight="600" fill="#1f2937">${label}</text>`;
        svg += `<text x="${x + w/2}" y="${y + h/2 + 10}" text-anchor="middle" font-size="8" fill="#6b7280">${r.w}×${r.h}mm</text>`;
    });

    // 绘制走廊（估算位置）
    if (corridor) {
        const ys = rooms.map(r => r.y + r.h).concat(rooms.map(r => r.y));
        const midY = Math.min(...ys);
        const cx = (0 - minX) * SCALE + MARGIN;
        const cy = (midY - corridor.h - minY) * SCALE + MARGIN;
        const cw = corridor.w * SCALE;
        const ch = corridor.h * SCALE;
        svg += `<rect x="${cx}" y="${cy}" width="${cw}" height="${ch}" fill="#e0f2fe" stroke="#0891b2" stroke-width="2" stroke-dasharray="6,4" rx="2"/>`;
        svg += `<text x="${cx + cw/2}" y="${cy + ch/2}" text-anchor="middle" font-size="11" font-weight="600" fill="#0e7490">CORRIDOR</text>`;
    }

    // 绘制疏散箭头（房间 → 走廊 → 出口）
    if (rooms.length > 1) {
        rooms.forEach(r => {
            const roomCx = (r.x + r.w / 2 - minX) * SCALE + MARGIN;
            // 假设门在靠近走廊的一侧（y 最小的房间门在下边，y 最大的房间门在上边）
            const doorYRoom = r.y + r.h;
            const corridorTop = Math.min(...rooms.map(rr => rr.y + rr.h));
            const toY = corridorTop;

            // 门 → 走廊
            const doorX = (r.x + r.w * 0.075 - minX) * SCALE + MARGIN;
            const doorY = (doorYRoom - minY) * SCALE + MARGIN;
            const toX = (r.x + r.w / 2 - minX) * SCALE + MARGIN;
            const toDoorY = (toY - minY) * SCALE + MARGIN;

            // 走廊中心
            const corridorY = Math.min(...rooms.map(rr => rr.y + rr.h));
            const toCorridorY = (corridorY - minY) * SCALE + MARGIN;

            // 简化：从房间下边中点画箭头到走廊中心
            const arrowStartX = roomCx;
            const arrowStartY = doorY + 4;
            const arrowEndX = (r.x + r.w / 2 - minX) * SCALE + MARGIN;
            const arrowEndY = toCorridorY - 4;
            if (arrowEndY > arrowStartY) {
                svg += `<line x1="${arrowStartX}" y1="${arrowStartY}" x2="${arrowEndX}" y2="${arrowEndY}" stroke="#ef4444" stroke-width="2" marker-end="url(#arrow-evac)"/>`;
            }
        });

        // 走廊 → 出口（走廊右侧外）
        const corridorY2 = Math.min(...rooms.map(rr => rr.y + rr.h));
        const corrCX = (0 + (corridor ? corridor.w : 3000) / 2 - minX) * SCALE + MARGIN;
        const corrCY = (corridorY2 - minY) * SCALE + MARGIN;
        const exitX = (corridor ? corridor.w : 3000) * SCALE + MARGIN;
        if (exitX > corrCX) {
            svg += `<line x1="${corrCX}" y1="${corrCY}" x2="${exitX - 20}" y2="${corrCY}" stroke="#ef4444" stroke-width="2" marker-end="url(#arrow-evac)"/>`;
            svg += `<text x="${exitX - 15}" y="${corrCY - 8}" text-anchor="middle" font-size="10" fill="#dc2626" font-weight="700">出口 →</text>`;
        }
    }

    // 验证标记
    if (validation && validation.fail_count > 0) {
        svg += `<text x="${svgW/2}" y="${svgH - 10}" text-anchor="middle" font-size="12" fill="#ef4444" font-weight="700">⚠️ ${validation.fail_count} 项违规</text>`;
    } else if (validation && validation.all_pass) {
        svg += `<text x="${svgW/2}" y="${svgH - 10}" text-anchor="middle" font-size="12" fill="#16a34a" font-weight="700">✅ 闭环验证通过</text>`;
    }

    // 比例尺
    const scaleLen = 2000 * SCALE;  // 2000mm = 2m
    const scaleY = svgH - 25;
    svg += `<line x1="20" y1="${scaleY}" x2="${20 + scaleLen}" y2="${scaleY}" stroke="#374151" stroke-width="2"/>`;
    svg += `<line x1="20" y1="${scaleY - 4}" x2="20" y2="${scaleY + 4}" stroke="#374151" stroke-width="1.5"/>`;
    svg += `<line x1="${20 + scaleLen}" y1="${scaleY - 4}" x2="${20 + scaleLen}" y2="${scaleY + 4}" stroke="#374151" stroke-width="1.5"/>`;
    svg += `<text x="${20 + scaleLen/2}" y="${scaleY - 6}" text-anchor="middle" font-size="8" fill="#6b7280">2m</text>`;

    svg += '</svg>';
    return svg;
}

/** 展开 SVG 到全屏弹窗 */
function expandReverseSVG() {
    const layout = window._reverseSVGLayout;
    if (!layout) return alert('先生成布局');
    const modal = document.createElement('div');
    modal.className = 'fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4';
    modal.innerHTML = `
        <div class="bg-white rounded-lg shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col">
            <div class="flex items-center justify-between p-4 border-b">
                <h3 class="font-bold">布局可视化</h3>
                <button onclick="this.closest('div.fixed').remove()" class="text-gray-400 hover:text-gray-600 text-2xl">&times;</button>
            </div>
            <div class="flex-1 overflow-auto p-4">` + renderLayoutSVG(layout, window._reverseSVGValidation) + `
            </div>
        </div>`;
    document.body.appendChild(modal);
    modal.addEventListener('click', e => { if (e.target === modal) modal.remove(); });
}

/** 下载 SVG 文件 */
function downloadReverseSVG() {
    const svgEl = document.querySelector('#reverse-svg svg');
    if (!svgEl) return alert('先生成布局');
    const blob = new Blob([svgEl.outerHTML], {type: 'image/svg+xml'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'baa-layout.svg';
    a.click();
    URL.revokeObjectURL(a.href);
}

// 页面加载时自动加载原子函数库
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(loadFunctions, 1000);
});