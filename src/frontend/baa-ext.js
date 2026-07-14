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

        const v = data.validation || {};
        validation.innerHTML = '<span class="' + (v.all_pass ? 'text-green-600' : 'text-red-600') + ' font-bold">' +
            (v.all_pass ? '✅ 全部通过' : '❌ ' + v.fail_count + ' FAIL') +
            '</span> 实体: ' + JSON.stringify(v.entities || {});

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

async function generateMultiReverse() {
    const result = document.getElementById('multi-reverse-result');
    const err = document.getElementById('multi-reverse-error');
    if (!result) return;
    const layoutDiv = document.getElementById('multi-reverse-layout');
    const dxfPre = document.getElementById('multi-reverse-dxf');
    const validationDiv = document.getElementById('multi-reverse-validation');
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

        // 显示布局信息
        const l = data.layout;
        let html = '<table class="w-full text-sm">' +
            '<thead><tr class="text-left text-gray-500"><th class="py-1">房间</th><th class="py-1">位置</th><th class="py-1">尺寸</th></tr></thead><tbody>';
        l.rooms.forEach(r => {
            html += '<tr><td class="py-1">' + r.type + '</td>' +
                '<td class="py-1">(' + r.x + ', ' + r.y + ')</td>' +
                '<td class="py-1">' + r.w + ' x ' + r.h + ' mm</td></tr>';
        });
        if (l.corridor) {
            html += '<tr class="text-blue-600"><td class="py-1">走廊</td>' +
                '<td class="py-1">—</td>' +
                '<td class="py-1">' + l.corridor.w + ' x ' + l.corridor.h + ' mm</td></tr>';
        }
        html += '</tbody></table>';
        layoutDiv.innerHTML = html;

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

// 页面加载时自动加载原子函数库
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(loadFunctions, 1000);
});