// BAA 产品力评估报告 · 图表脚本
(function () {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();

  var axisCommon = {
    axisLine: { lineStyle: { color: rule } },
    axisTick: { show: false },
    axisLabel: { color: muted, fontSize: 11 },
    splitLine: { lineStyle: { color: rule, type: 'dashed' } }
  };

  // ── 图 1：审查耗时（对数刻度） ──
  var perf = echarts.init(document.getElementById('chart-perf'), null, { renderer: 'svg' });
  perf.setOption({
    animation: false,
    grid: { left: 130, right: 28, top: 44, bottom: 28 },
    legend: {
      top: 8, left: 0, itemWidth: 10, itemHeight: 10, itemGap: 18,
      textStyle: { color: muted, fontSize: 11 }
    },
    tooltip: {
      trigger: 'axis', appendToBody: true,
      axisPointer: { type: 'shadow' },
      valueFormatter: function (v) { return v == null ? '—' : v + ' s'; }
    },
    xAxis: {
      type: 'log', min: 1, max: 200, name: '秒', nameTextStyle: { color: muted, fontSize: 11 },
      axisLine: { lineStyle: { color: rule } },
      axisTick: { show: false },
      axisLabel: { color: muted, fontSize: 11, formatter: function (v) { return v + 's'; } },
      splitLine: { lineStyle: { color: rule, type: 'dashed' } }
    },
    yAxis: {
      type: 'category',
      data: ['电气图 · 3003 图元', '机电图 · 4582 图元', '建筑图 · 5334 图元'],
      axisLine: { lineStyle: { color: rule } },
      axisTick: { show: false },
      axisLabel: { color: ink, fontSize: 11 }
    },
    series: [
      {
        name: '优化前', type: 'bar', barWidth: 14,
        data: [46.4, null, 108.8],
        itemStyle: { color: accent2, opacity: 0.75 },
        label: { show: true, position: 'right', color: accent2, fontSize: 11, formatter: function (p) { return p.value == null ? '' : p.value + 's'; } }
      },
      {
        name: '优化后', type: 'bar', barWidth: 14,
        data: [1.5, 5.1, 28.7],
        itemStyle: { color: accent },
        label: { show: true, position: 'right', color: accent, fontSize: 11, formatter: function (p) { return p.value + 's'; } }
      }
    ]
  });
  window.addEventListener('resize', function () { perf.resize(); });

  // ── 图 2：十维雷达（环比） ──
  var dims = [
    '方向价值', '原子函数/判定', '语义/拓扑', '解析架构', '视觉模型',
    '产品工作流', '工程质量', '安全/合规', '可观测/运维', '商业化'
  ];
  var before = [4.2, 3.2, 2.2, 2.4, 1.0, 2.2, 2.6, 2.0, 1.8, 1.5];
  var now = [4.2, 3.2, 2.0, 2.6, 1.0, 2.4, 3.1, 1.7, 2.2, 1.5];

  var radar = echarts.init(document.getElementById('chart-radar'), null, { renderer: 'svg' });
  radar.setOption({
    animation: false,
    legend: {
      top: 6, left: 0, itemWidth: 10, itemHeight: 10, itemGap: 18,
      textStyle: { color: muted, fontSize: 11 }
    },
    tooltip: { trigger: 'item', appendToBody: true },
    radar: {
      center: ['50%', '56%'],
      radius: '62%',
      indicator: dims.map(function (d) { return { name: d, max: 5 }; }),
      axisName: { color: ink, fontSize: 11 },
      splitLine: { lineStyle: { color: rule } },
      splitArea: { show: false },
      axisLine: { lineStyle: { color: rule } }
    },
    series: [{
      type: 'radar',
      symbolSize: 4,
      data: [
        {
          name: '2026-10-16', value: before,
          lineStyle: { color: muted, width: 1.5, type: 'dashed' },
          itemStyle: { color: muted },
          areaStyle: { color: muted + '14' }
        },
        {
          name: '2026-11-03', value: now,
          lineStyle: { color: accent, width: 2 },
          itemStyle: { color: accent },
          areaStyle: { color: accent + '22' }
        }
      ]
    }]
  });
  window.addEventListener('resize', function () { radar.resize(); });
})();
