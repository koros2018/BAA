// charts.js — BAA P131 Fix Report Visualizations
(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var accent3 = style.getPropertyValue('--accent3').trim();
  var blue = style.getPropertyValue('--blue').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var inkDim = style.getPropertyValue('--ink-dim').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();
  var bg3 = style.getPropertyValue('--bg3').trim();

  // --- Chart 1: Root Cause Contribution (Pie) ---
  var chart1 = echarts.init(document.getElementById('chart-root-causes'), null, { renderer: 'svg' });
  chart1.setOption({
    tooltip: { appendToBody: true, trigger: 'item', formatter: '{b}: {c} 条 ({d}%)' },
    legend: {
      bottom: 0,
      textStyle: { color: inkDim, fontSize: 12 },
      itemWidth: 12, itemHeight: 12, itemGap: 18
    },
    series: [{
      type: 'pie',
      radius: ['45%', '72%'],
      center: ['50%', '42%'],
      avoidLabelOverlap: true,
      itemStyle: { borderColor: bg2, borderWidth: 3, borderRadius: 3 },
      label: { show: false },
      emphasis: {
        label: { show: true, fontSize: 14, fontWeight: 600, color: ink }
      },
      data: [
        { value: 20, name: '聚合语义越界（DIM-006/113）', itemStyle: { color: accent2 } },
        { value: 7, name: '扫线法派生非建筑空间', itemStyle: { color: blue } },
        { value: 4, name: '立面图误识别', itemStyle: { color: accent3 } },
        { value: 1, name: '墙体未合龙 polygon 偏小', itemStyle: { color: accent } },
        { value: 32, name: '其他（小构件/TEXT 误分类等）', itemStyle: { color: muted } }
      ]
    }]
  });
  window.addEventListener('resize', function() { chart1.resize(); });

  // --- Chart 2: Fix Timeline (Bar) ---
  var chart2 = echarts.init(document.getElementById('chart-timeline'), null, { renderer: 'svg' });
  chart2.setOption({
    tooltip: { appendToBody: true, trigger: 'axis' },
    grid: { top: 40, bottom: 80, left: 80, right: 30 },
    xAxis: {
      type: 'category',
      data: ['初始\n4107', '阶段 1-4\n35', '阶段 5\n专家复核\n7', '阶段 6\n图纸过滤\n1', '阶段 7\n面积校正\n0'],
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: inkDim, fontSize: 11, lineHeight: 15 },
      axisTick: { show: false }
    },
    yAxis: {
      type: 'value',
      name: 'findings 数',
      nameTextStyle: { color: muted, fontSize: 11 },
      axisLine: { show: false },
      axisLabel: { color: inkDim, fontSize: 11 },
      splitLine: { lineStyle: { color: rule, type: 'dashed' } }
    },
    series: [{
      type: 'bar',
      data: [
        { value: 4107, itemStyle: { color: accent2 } },
        { value: 35, itemStyle: { color: accent3 } },
        { value: 7, itemStyle: { color: blue } },
        { value: 1, itemStyle: { color: accent } },
        { value: 0, itemStyle: { color: accent } }
      ],
      barWidth: 48,
      itemStyle: { borderRadius: [6, 6, 0, 0] },
      label: {
        show: true,
        position: 'top',
        formatter: function(p) { return p.value === 0 ? '✓' : p.value.toLocaleString(); },
        color: ink, fontSize: 13, fontWeight: 700
      }
    }],
    animation: false
  });
  window.addEventListener('resize', function() { chart2.resize(); });

  // --- Chart 3: Before vs After (Stacked Bar) ---
  var chart3 = echarts.init(document.getElementById('chart-compare'), null, { renderer: 'svg' });
  chart3.setOption({
    tooltip: { appendToBody: true, trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: {
      top: 0,
      textStyle: { color: inkDim, fontSize: 12 },
      itemWidth: 12, itemHeight: 12
    },
    grid: { top: 50, bottom: 30, left: 80, right: 30 },
    xAxis: {
      type: 'category',
      data: ['建筑图\n(8张)', '结构图\n(14张)', '暖通图\n(9张)', '电气图\n(0张)', '不支持\n(1张)'],
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: inkDim, fontSize: 11 },
      axisTick: { show: false }
    },
    yAxis: {
      type: 'value',
      name: '平均 findings / 张',
      nameTextStyle: { color: muted, fontSize: 11 },
      axisLine: { show: false },
      axisLabel: { color: inkDim, fontSize: 11 },
      splitLine: { lineStyle: { color: rule, type: 'dashed' } }
    },
    series: [
      {
        name: '修复前',
        type: 'bar',
        data: [
          { value: 26.3, itemStyle: { color: accent2 } },
          { value: 218.5, itemStyle: { color: accent2, opacity: 0.7 } },
          { value: 0.7, itemStyle: { color: accent2, opacity: 0.5 } },
          { value: 0 },
          { value: 0 }
        ],
        barWidth: 22,
        barGap: '-100%',
        itemStyle: { borderRadius: [4, 4, 0, 0] }
      },
      {
        name: '修复后',
        type: 'bar',
        data: [
          { value: 0, itemStyle: { color: accent } },
          { value: 0, itemStyle: { color: blue } },
          { value: 0, itemStyle: { color: blue } },
          { value: 0 },
          { value: 0 }
        ],
        barWidth: 22,
        itemStyle: { borderRadius: [4, 4, 0, 0] },
        label: {
          show: true,
          position: 'top',
          formatter: function(p) { return p.value === 0 ? '0 ✓' : p.value; },
          color: accent, fontSize: 11, fontWeight: 600
        }
      }
    ],
    animation: false
  });
  window.addEventListener('resize', function() { chart3.resize(); });

})();
