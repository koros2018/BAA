<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <title>Blueprint AI Agent | 图纸智能体</title>
    <!-- Tailwind CSS + Font Awesome + Chart.js -->
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdn.jsdelivr.net/npm/font-awesome@4.7.0/css/font-awesome.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.8/dist/chart.umd.min.js"></script>
    <style>
        /* 自定义windows风格增强 */
        body {
            background: #f0f2f5;
            font-family: 'Segoe UI', 'Inter', system-ui, sans-serif;
        }
        .card {
            transition: all 0.2s ease;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05), 0 1px 2px rgba(0,0,0,0.03);
        }
        .card:hover {
            box-shadow: 0 10px 20px -5px rgba(0,0,0,0.1);
            transform: translateY(-2px);
        }
        .drag-active {
            border: 2px dashed #3b82f6;
            background-color: #eff6ff;
        }
        .scrollbar-thin::-webkit-scrollbar {
            width: 6px;
            height: 6px;
        }
        .scrollbar-thin::-webkit-scrollbar-track {
            background: #e2e8f0;
            border-radius: 10px;
        }
        .scrollbar-thin::-webkit-scrollbar-thumb {
            background: #94a3b8;
            border-radius: 10px;
        }
        .iteration-step {
            border-left: 3px solid #3b82f6;
        }
    </style>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        primary: '#1e40af',
                        secondary: '#3b82f6',
                        accent: '#f97316',
                    }
                }
            }
        }
    </script>
</head>
<body class="bg-gray-100 antialiased">
    <div class="flex flex-col h-screen">
        <!-- 顶部导航栏（windows风格标题栏） -->
        <header class="bg-gradient-to-r from-[#1e3a8a] to-[#3b82f6] text-white shadow-md px-6 py-3 flex justify-between items-center">
            <div class="flex items-center gap-3">
                <i class="fa fa-cubes text-2xl"></i>
                <h1 class="text-xl font-semibold tracking-wide">Blueprint AI Agent · 图纸智能体</h1>
                <span class="bg-white/20 text-xs px-2 py-1 rounded-full ml-2">闭环修正 v1.0</span>
            </div>
            <div class="flex gap-3">
                <button class="hover:bg-white/20 px-3 py-1 rounded-md transition"><i class="fa fa-bell-o"></i></button>
                <button class="hover:bg-white/20 px-3 py-1 rounded-md transition"><i class="fa fa-user-circle"></i> 设计师</button>
            </div>
        </header>

        <div class="flex flex-1 overflow-hidden">
            <!-- 左侧导航栏（经典分页） -->
            <aside class="w-64 bg-white shadow-md z-10 flex-shrink-0 overflow-y-auto">
                <nav class="py-4 px-3 space-y-1">
                    <button data-nav="dashboard" class="nav-btn w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-gray-700 hover:bg-gray-100 transition bg-primary text-white">
                        <i class="fa fa-tachometer w-5"></i><span>系统概览</span>
                    </button>
                    <button data-nav="drawing" class="nav-btn w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-gray-700 hover:bg-gray-100 transition">
                        <i class="fa fa-file-image-o w-5"></i><span>图纸管理</span>
                    </button>
                    <button data-nav="standards" class="nav-btn w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-gray-700 hover:bg-gray-100 transition">
                        <i class="fa fa-book w-5"></i><span>规范与图集库</span>
                    </button>
                    <button data-nav="ai-review" class="nav-btn w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-gray-700 hover:bg-gray-100 transition">
                        <i class="fa fa-robot w-5"></i><span>AI审图与修正</span>
                    </button>
                    <button data-nav="compare" class="nav-btn w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-gray-700 hover:bg-gray-100 transition">
                        <i class="fa fa-columns w-5"></i><span>图纸对比演示</span>
                    </button>
                    <button data-nav="analysis" class="nav-btn w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-gray-700 hover:bg-gray-100 transition">
                        <i class="fa fa-bar-chart w-5"></i><span>结果分析</span>
                    </button>
                    <button data-nav="settings" class="nav-btn w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-gray-700 hover:bg-gray-100 transition">
                        <i class="fa fa-cog w-5"></i><span>系统设置</span>
                    </button>
                </nav>
                <div class="border-t border-gray-200 my-2 pt-4 px-4 text-xs text-gray-400">
                    <p>© 2025 Blueprint AI</p>
                    <p>闭环审图 | 自动修正</p>
                </div>
            </aside>

            <!-- 右侧主内容区域 -->
            <main class="flex-1 overflow-y-auto p-6 bg-gray-100">
                <!-- 1. 系统概览页 -->
                <div id="dashboard-page" class="page-container space-y-6">
                    <div class="flex justify-between items-center">
                        <h2 class="text-2xl font-bold text-gray-800">系统概览</h2>
                        <button class="bg-primary text-white px-4 py-2 rounded-lg shadow-sm hover:bg-primary-dark transition"><i class="fa fa-refresh mr-1"></i> 同步数据</button>
                    </div>
                    <!-- 统计卡片 -->
                    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
                        <div class="bg-white p-5 rounded-xl shadow-sm card"><div class="flex justify-between"><span class="text-gray-500">已入库图纸</span><i class="fa fa-file-pdf-o text-2xl text-primary"></i></div><p class="text-3xl font-bold mt-2">124</p><p class="text-sm text-gray-400">+12 本周</p></div>
                        <div class="bg-white p-5 rounded-xl shadow-sm card"><div class="flex justify-between"><span class="text-gray-500">规范条款</span><i class="fa fa-gavel text-2xl text-primary"></i></div><p class="text-3xl font-bold mt-2">3,287</p><p class="text-sm text-gray-400">国标/行标</p></div>
                        <div class="bg-white p-5 rounded-xl shadow-sm card"><div class="flex justify-between"><span class="text-gray-500">自动修正成功率</span><i class="fa fa-check-circle-o text-2xl text-green-500"></i></div><p class="text-3xl font-bold mt-2">87.3%</p><p class="text-sm text-gray-400">最近50次迭代</p></div>
                        <div class="bg-white p-5 rounded-xl shadow-sm card"><div class="flex justify-between"><span class="text-gray-500">AI Agent 闭环任务</span><i class="fa fa-cogs text-2xl text-primary"></i></div><p class="text-3xl font-bold mt-2">342</p><p class="text-sm text-gray-400">本月完成</p></div>
                    </div>
                    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <div class="bg-white p-5 rounded-xl shadow-sm"><h3 class="font-semibold mb-3">📊 规范违反TOP5</h3><canvas id="violationChart" height="200"></canvas></div>
                        <div class="bg-white p-5 rounded-xl shadow-sm"><h3 class="font-semibold mb-3">🔄 修正迭代收敛曲线</h3><canvas id="convergenceChart" height="200"></canvas></div>
                    </div>
                    <div class="bg-white p-5 rounded-xl shadow-sm"><h3 class="font-semibold mb-2">📌 近期活动</h3><div class="space-y-2 text-sm"><p><i class="fa fa-check-circle text-green-500 mr-2"></i> AI完成“综合办公楼”结构图自动修正 (违规数 5→0)</p><p><i class="fa fa-upload text-blue-500 mr-2"></i> 上传最新国标《防火规范》GB50016-2023 已解析入库</p><p><i class="fa fa-refresh text-orange-500 mr-2"></i> SubAgent002 生成式模块已更新参数模板</p></div></div>
                </div>

                <!-- 2. 图纸管理页 -->
                <div id="drawing-page" class="page-container hidden space-y-6">
                    <div class="flex justify-between"><h2 class="text-2xl font-bold">图纸资产库</h2><button class="bg-primary text-white px-4 py-2 rounded-lg"><i class="fa fa-upload"></i> 上传图纸(DWG/PDF)</button></div>
                    <div class="bg-white rounded-xl shadow-sm overflow-hidden">
                        <table class="min-w-full divide-y"><thead class="bg-gray-50"><tr><th class="px-6 py-3 text-left text-xs">图纸名称</th><th>专业</th><th>版本</th><th>合规状态</th><th>操作</th></tr></thead>
                        <tbody class="divide-y">
                            <tr><td class="px-6 py-3">办公楼_建筑平面图_v2.dwg</td><td>建筑</td><td>v2.1</td><td><span class="bg-green-100 text-green-700 px-2 rounded-full text-xs">已合规</span></td><td><button class="text-primary">审图</button> | <button class="text-primary">下载</button></td></tr>
                            <tr><td class="px-6 py-3">商业楼_结构施工图.dwg</td><td>结构</td><td>v1.0</td><td><span class="bg-yellow-100 text-yellow-700 px-2 rounded-full text-xs">修正中</span></td><td><button class="text-primary">继续修正</button></td></tr>
                            <tr><td class="px-6 py-3">地下车库_暖通.dwg</td><td>暖通</td><td>v0.9</td><td><span class="bg-red-100 text-red-700 px-2 rounded-full text-xs">待审图</span></td><td><button class="text-primary">一键AI分析</button></td></tr>
                        </tbody></table>
                    </div>
                    <div class="bg-white p-5 rounded-xl border-2 border-dashed border-gray-300 text-center hover:border-primary transition"><i class="fa fa-cloud-upload text-3xl text-gray-400"></i><p class="mt-1">拖拽图纸至此区域，自动解析并启动审图流程</p></div>
                </div>

                <!-- 3. 规范与图集库 (独立知识库) -->
                <div id="standards-page" class="page-container hidden space-y-6">
                    <div class="flex justify-between"><h2 class="text-2xl font-bold">📚 规范标准库 & 图集向量库</h2><button class="bg-gray-200 px-3 py-1 rounded"><i class="fa fa-plus"></i> 导入规范</button></div>
                    <div class="grid grid-cols-2 gap-5">
                        <div class="bg-white rounded-xl p-4 shadow-sm"><i class="fa fa-balance-scale text-primary mr-2"></i><span class="font-semibold">国标强条库</span><span class="float-right text-gray-400">1,842条</span><div class="text-xs text-gray-500 mt-2">GB50010, GB50016, JGJ3... 结构化JSON</div></div>
                        <div class="bg-white rounded-xl p-4 shadow-sm"><i class="fa fa-picture-o text-primary mr-2"></i><span class="font-semibold">标准图集向量库</span><span class="float-right text-gray-400">312个图集</span><div class="text-xs text-gray-500 mt-2">12J系列, 22G101 等解构向量特征</div></div>
                    </div>
                    <div class="bg-white rounded-xl shadow-sm"><div class="p-4 border-b"><input type="text" placeholder="🔍 检索规范条款 (例如: 楼梯踏步宽度)" class="w-full p-2 border rounded"></div><div class="p-2 max-h-64 overflow-auto"><p class="p-2 hover:bg-gray-50">GB50016-2023 第5.5.18条: 高层公共建筑疏散楼梯净宽≥1.2m</p><p class="p-2 hover:bg-gray-50">GB50010 第8.3.1条: 混凝土保护层厚度...</p><p class="p-2 hover:bg-gray-50">JGJ 3-2010 第7.2.15条: 剪力墙边缘构件...</p></div></div>
                </div>

                <!-- 4. AI审图与修正（闭环核心） -->
                <div id="ai-review-page" class="page-container hidden space-y-6">
                    <div class="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-xl p-5 shadow-sm">
                        <h2 class="text-2xl font-bold flex items-center gap-2"><i class="fa fa-magic text-primary"></i> AI Agent 自动审图 + 闭环修正</h2>
                        <p class="text-gray-600 mt-1">上传图纸 → 智能解构 → 规范比对 → 自主修正 → 重复迭代直至100%合规</p>
                    </div>
                    <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
                        <div class="bg-white rounded-xl p-5 shadow-sm">
                            <label class="font-semibold">当前待审图纸</label>
                            <div class="border-2 border-dashed rounded-lg p-6 text-center mt-2 bg-gray-50" id="dragZone">
                                <i class="fa fa-file-pdf-o text-3xl text-gray-400"></i>
                                <p class="text-sm text-gray-500">点击或拖拽上传DWG/PDF</p>
                                <input type="file" class="hidden" id="fileInput" accept=".dwg,.pdf">
                            </div>
                            <div class="mt-4 flex gap-2">
                                <button id="startReviewBtn" class="bg-primary text-white px-4 py-2 rounded-lg flex-1"><i class="fa fa-play"></i> 一键AI分析+审图</button>
                                <button id="startOptimizeBtn" class="bg-green-600 text-white px-4 py-2 rounded-lg flex-1"><i class="fa fa-wrench"></i> 一键图纸优化</button>
                            </div>
                        </div>
                        <div class="bg-white rounded-xl p-5 shadow-sm">
                            <h3 class="font-semibold">📋 审图意见 / 修正历史</h3>
                            <div id="reviewLog" class="h-48 overflow-y-auto text-sm space-y-2 border-t mt-2 pt-2">
                                <div class="text-gray-400 italic">尚未执行审图，请上传图纸并启动AI分析</div>
                            </div>
                        </div>
                    </div>
                    <div class="bg-white rounded-xl shadow-sm p-4">
                        <div class="flex justify-between items-center"><h3 class="font-semibold">🔄 迭代修正过程监控</h3><span class="text-xs text-gray-400">迭代次数: <span id="iterCount">0</span> / 最大20</span></div>
                        <div class="w-full bg-gray-200 rounded-full h-2.5 mt-2"><div id="iterProgress" class="bg-primary h-2.5 rounded-full" style="width:0%"></div></div>
                        <div id="iterSteps" class="mt-3 max-h-36 overflow-y-auto text-xs space-y-1"></div>
                    </div>
                </div>

                <!-- 5. 图纸对比演示（前后滑动对比） -->
                <div id="compare-page" class="page-container hidden space-y-6">
                    <h2 class="text-2xl font-bold">📐 图纸修改前后对比</h2>
                    <div class="bg-white rounded-xl p-5 flex flex-col lg:flex-row gap-4 items-center">
                        <div class="flex-1 text-center border rounded-lg p-3"><i class="fa fa-image text-4xl text-gray-300"></i><p class="text-sm mt-1">原始图纸</p><div class="bg-gray-100 h-48 flex items-center justify-center"><span class="text-gray-400">示意图 | 原始构件</span></div></div>
                        <div class="text-2xl text-primary"><i class="fa fa-arrow-right"></i></div>
                        <div class="flex-1 text-center border rounded-lg p-3"><i class="fa fa-check-circle text-4xl text-green-400"></i><p class="text-sm mt-1">优化后图纸 (AI修正)</p><div class="bg-gray-100 h-48 flex items-center justify-center"><span class="text-gray-400">合规修正版 | 墙体厚度/门窗移位</span></div></div>
                    </div>
                    <div class="bg-white rounded-xl p-5"><h3 class="font-semibold">🔍 热力图 (AI关注区域)</h3><div class="bg-gradient-to-br from-gray-200 to-gray-300 h-48 rounded-lg flex items-center justify-center text-gray-500"><i class="fa fa-fire mr-1"></i> 合规高亮区域: 楼梯疏散宽度、防火墙构造</div></div>
                </div>

                <!-- 6. 结果分析 -->
                <div id="analysis-page" class="page-container hidden space-y-6">
                    <h2 class="text-2xl font-bold">📊 合规结果 & 错误分析</h2>
                    <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
                        <div class="bg-white rounded-xl p-5 shadow-sm"><h3>🧩 常见违反条款分布</h3><canvas id="pieViolation" height="200"></canvas></div>
                        <div class="bg-white rounded-xl p-5 shadow-sm"><h3>📈 模型准确率演变</h3><canvas id="accuracyTrend" height="200"></canvas></div>
                    </div>
                    <div class="bg-white rounded-xl p-5"><h3 class="font-semibold">⚠️ 混淆矩阵 (构件识别)</h3><div class="overflow-x-auto"><table class="min-w-full text-sm"><thead><tr><th></th><th>剪力墙</th><th>框架梁</th><th>楼梯</th><th>门窗</th></tr></thead><tbody><tr><td class="font-medium">真实:剪力墙</td><td>0.92</td><td>0.05</td><td>0.02</td><td>0.01</td></tr><tr><td>真实:框架梁</td><td>0.07</td><td>0.88</td><td>0.03</td><td>0.02</td></tr></tbody></table></div></div>
                </div>

                <!-- 7. 系统设置 -->
                <div id="settings-page" class="page-container hidden space-y-6">
                    <h2 class="text-2xl font-bold">⚙️ 系统设置</h2>
                    <div class="bg-white rounded-xl p-5 space-y-4">
                        <div><label class="block font-medium">CAD解析内核</label><select class="border rounded p-2 w-full"><option>ODA Drawings SDK (商业)</option><option>开源转换器 (DXF中间格式)</option></select></div>
                        <div><label class="block font-medium">规范版本偏好</label><div class="flex gap-2"><button class="border px-3 py-1 rounded bg-primary text-white">GB50016-2023</button><button class="border px-3 py-1 rounded">JGJ3-2010</button></div></div>
                        <div><label class="block font-medium">迭代最大次数</label><input type="number" value="15" class="border rounded p-2 w-32"></div>
                        <div><label class="block font-medium">自动保存过程资料</label><input type="checkbox" checked> 启用全生命周期记录</div>
                    </div>
                </div>
            </main>
        </div>
    </div>

    <script>
        // 页面切换逻辑
        const pages = ['dashboard','drawing','standards','ai-review','compare','analysis','settings'];
        const navBtns = document.querySelectorAll('.nav-btn');
        function showPage(pageId) {
            pages.forEach(p => {
                const el = document.getElementById(`${p}-page`);
                if(el) el.classList.add('hidden');
            });
            const active = document.getElementById(`${pageId}-page`);
            if(active) active.classList.remove('hidden');
            navBtns.forEach(btn => {
                btn.classList.remove('bg-primary','text-white');
                btn.classList.add('text-gray-700');
                if(btn.getAttribute('data-nav') === pageId) {
                    btn.classList.add('bg-primary','text-white');
                }
            });
        }
        navBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const nav = btn.getAttribute('data-nav');
                showPage(nav);
            });
        });
        showPage('dashboard');

        // 模拟图表绘制
        const violationCtx = document.getElementById('violationChart')?.getContext('2d');
        if(violationCtx) new Chart(violationCtx, { type:'bar', data:{ labels:['楼梯宽度不足','防火分区超限','钢筋保护层','门窗开启方向'], datasets:[{label:'违规次数', data:[23,17,12,9], backgroundColor:'#3b82f6'}] } });
        const convergenceCtx = document.getElementById('convergenceChart')?.getContext('2d');
        if(convergenceCtx) new Chart(convergenceCtx, { type:'line', data:{ labels:['迭代1','2','3','4','5','6'], datasets:[{label:'剩余违规数', data:[12,7,4,2,0,0], borderColor:'#f97316'}] } });
        const pieCtx = document.getElementById('pieViolation')?.getContext('2d');
        if(pieCtx) new Chart(pieCtx, { type:'pie', data:{ labels:['疏散宽度','耐火等级','结构配筋','其他'], datasets:[{data:[42,28,20,10], backgroundColor:['#f97316','#3b82f6','#10b981','#94a3b8']}] } });
        const trendCtx = document.getElementById('accuracyTrend')?.getContext('2d');
        if(trendCtx) new Chart(trendCtx, { type:'line', data:{ labels:['1月','2月','3月','4月','5月'], datasets:[{label:'识别准确率', data:[72,78,83,86,89]}] } });

        // AI审图与修正模块模拟 (一键AI分析 + 迭代过程)
        const dragZone = document.getElementById('dragZone');
        const fileInput = document.getElementById('fileInput');
        const reviewLogDiv = document.getElementById('reviewLog');
        const startReviewBtn = document.getElementById('startReviewBtn');
        const startOptimizeBtn = document.getElementById('startOptimizeBtn');
        const iterCountSpan = document.getElementById('iterCount');
        const iterProgressDiv = document.getElementById('iterProgress');
        const iterStepsDiv = document.getElementById('iterSteps');

        let currentIter = 0;
        let simulatedIntervals = null;

        function resetIterDisplay() {
            currentIter = 0;
            iterCountSpan.innerText = '0';
            iterProgressDiv.style.width = '0%';
            iterStepsDiv.innerHTML = '';
        }

        function addLogMessage(msg, type='info') {
            const div = document.createElement('div');
            div.className = `text-sm ${type==='error'?'text-red-600':'text-gray-700'} border-b pb-1`;
            div.innerHTML = `<i class="fa ${type==='error'?'fa-exclamation-circle':'fa-info-circle'} mr-1"></i> ${msg}`;
            reviewLogDiv.appendChild(div);
            reviewLogDiv.scrollTop = reviewLogDiv.scrollHeight;
        }

        // 模拟AI分析
        startReviewBtn.addEventListener('click', () => {
            if(!dragZone.querySelector('input')?.files?.length && !window.mockFileFlag) {
                addLogMessage('请先上传图纸 (模拟演示，将自动生成样例)', 'info');
                window.mockFileFlag = true;
            }
            addLogMessage('🔍 启动AI图纸解析与规范比对...', 'info');
            setTimeout(() => {
                addLogMessage('📐 解构完成: 识别墙体24处，楼梯2部，门窗16樘', 'info');
                setTimeout(() => {
                    addLogMessage('⚠️ 发现5处违规: ①楼梯踏步宽度260mm不足(规范≥280mm) ②外墙保温材料缺失③防火分区超面积...', 'error');
                    addLogMessage('🤖 Agent自动生成修正策略: 调整楼梯踏步宽度至290mm, 增加防火卷帘', 'info');
                }, 800);
            }, 600);
        });

        // 一键图纸优化 + 模拟迭代闭环
        startOptimizeBtn.addEventListener('click', () => {
            if(reviewLogDiv.innerHTML.includes('未执行审图') && !window.mockFileFlag) {
                addLogMessage('请先点击“一键AI分析+审图”或上传图纸', 'error');
                return;
            }
            resetIterDisplay();
            addLogMessage('🚀 启动闭环优化: 目标 100% 合规');
            let violationCount = 5;
            let step = 0;
            const maxIter = 8;
            const interval = setInterval(() => {
                if(step >= maxIter) {
                    clearInterval(interval);
                    addLogMessage('✅ 迭代完成！所有违规项已修正，图纸合规率100%，输出正式图纸', 'info');
                    iterCountSpan.innerText = step;
                    iterProgressDiv.style.width = '100%';
                    return;
                }
                step++;
                violationCount = Math.max(0, violationCount - Math.floor(Math.random()*2) - (step>2?1:0));
                iterCountSpan.innerText = step;
                const percent = (step / maxIter)*100;
                iterProgressDiv.style.width = `${percent}%`;
                const stepDiv = document.createElement('div');
                stepDiv.className = 'iteration-step pl-2 py-1 text-xs';
                stepDiv.innerHTML = `<span class="font-mono">[迭代${step}]</span> 剩余违规数: ${violationCount}  → 执行修正操作: ${violationCount===0?'全部合规，生成新图':(violationCount>2?'调整楼梯参数/修正墙体厚度':'微调防火分区')}`;
                iterStepsDiv.appendChild(stepDiv);
                iterStepsDiv.scrollTop = iterStepsDiv.scrollHeight;
                if(violationCount === 0) {
                    clearInterval(interval);
                    addLogMessage('🏆 自动修正闭环达成100%合规，图纸已重构存档', 'info');
                }
            }, 1200);
            simulatedIntervals = interval;
        });

        // 拖拽上传模拟
        dragZone.addEventListener('dragover', (e) => { e.preventDefault(); dragZone.classList.add('drag-active'); });
        dragZone.addEventListener('dragleave', () => dragZone.classList.remove('drag-active'));
        dragZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dragZone.classList.remove('drag-active');
            addLogMessage('📁 接收到图纸文件，开始预解析...', 'info');
            window.mockFileFlag = true;
            setTimeout(() => addLogMessage('解析完成: 图纸版本 DWG 2018, 包含建筑/结构图层', 'info'), 500);
        });
        dragZone.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', () => {
            if(fileInput.files.length) addLogMessage(`已选择: ${fileInput.files[0].name}`, 'info');
        });

        // 额外样式: 保持一致性
        const style = document.createElement('style');
        style.textContent = `.hidden{display:none;} .bg-primary-dark{background:#1e3a8a;}`;
        document.head.appendChild(style);
    </script>
</body>
</html>