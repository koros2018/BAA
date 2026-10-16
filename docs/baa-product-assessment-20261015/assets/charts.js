// assets/charts.js — BAA 评估报告图表
(function () {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim() || '#0F6E58';
  var accent2 = style.getPropertyValue('--accent2').trim() || '#B45309';
  var ink = style.getPropertyValue('--ink').trim() || '#17202B';
  var muted = style.getPropertyValue('--muted').trim() || '#5C6773';
  var rule = style.getPropertyValue('--rule').trim() || '#E2E5EA';
  var bg2 = style.getPropertyValue('--bg2').trim() || '#FFFFFF';
  var bg = style.getPropertyValue('--bg').trim() || '#FAFAF8';

  // ---- Fig 1: radar ----
  var radarEl = document.getElementById('chart-radar');
  if (radarEl) {
    var r = echarts.init(radarEl, null, { renderer: 'svg' });
    r.setOption({
      animation: false,
      tooltip: { appendToBody: true },
      radar: {
        indicator: [
          { name: '方向价值', max: 5 },
          { name: '解析架构', max: 5 },
          { name: '视觉模型', max: 5 },
          { name: '语义/拓扑', max: 5 },
          { name: '原子函数', max: 5 },
          { name: '产品工作流', max: 5 }
        ],
        radius: '62%',
        center: ['50%', '54%'],
        axisName: { color: ink, fontSize: 12 },
        splitLine: { lineStyle: { color: rule } },
        axisLine: { lineStyle: { color: rule } },
        splitArea: { areaStyle: { color: [bg2, bg] } }
      },
      series: [{
        type: 'radar',
        symbolSize: 5,
        data: [{
          value: [4.2, 2.4, 1.0, 2.2, 3.2, 2.2],
          name: '当前评级',
          areaStyle: { color: accent, opacity: 0.20 },
          lineStyle: { color: accent, width: 2 },
          itemStyle: { color: accent }
        }]
      }]
    });
    window.addEventListener('resize', function () { r.resize(); });
  }

  // ---- Fig 2: usable donut ----
  var usableEl = document.getElementById('chart-usable');
  if (usableEl) {
    var d = echarts.init(usableEl, null, { renderer: 'svg' });
    d.setOption({
      animation: false,
      tooltip: { appendToBody: true, trigger: 'item', formatter: '{b}：{c} 张（{d}%）' },
      legend: { bottom: 6, textStyle: { color: muted, fontSize: 12 }, itemWidth: 12, itemHeight: 12 },
      series: [{
        type: 'pie',
        radius: ['50%', '72%'],
        center: ['50%', '46%'],
        avoidLabelOverlap: true,
        label: { color: ink, fontSize: 11, formatter: '{c}' },
        itemStyle: { borderColor: bg2, borderWidth: 2 },
        data: [
          { value: 41, name: '可用', itemStyle: { color: accent } },
          { value: 84, name: '结构/大图跳过', itemStyle: { color: accent2 } },
          { value: 4, name: '超时', itemStyle: { color: muted } },
          { value: 6, name: '其他', itemStyle: { color: rule } }
        ]
      }]
    });
    window.addEventListener('resize', function () { d.resize(); });
  }

  // ---- Fig 3: mAP collapse bars ----
  var mapEl = document.getElementById('chart-map');
  if (mapEl) {
    var m = echarts.init(mapEl, null, { renderer: 'svg' });
    m.setOption({
      animation: false,
      tooltip: { appendToBody: true, trigger: 'axis', formatter: '{b}<br/>mAP50：{c}' },
      grid: { left: '10%', right: '6%', top: '12%', bottom: '14%' },
      xAxis: {
        type: 'category',
        data: ['合成数据基线', '真实图纸整体', '真实 · 墙体'],
        axisLabel: { color: muted, fontSize: 12 },
        axisLine: { lineStyle: { color: rule } },
        axisTick: { show: false }
      },
      yAxis: {
        type: 'value', max: 0.6,
        axisLabel: { color: muted, fontSize: 11, formatter: '{value}' },
        splitLine: { lineStyle: { color: rule } },
        axisLine: { show: false }
      },
      series: [{
        type: 'bar',
        barWidth: '44%',
        label: { show: true, position: 'top', color: ink, fontSize: 12, formatter: '{c}' },
        data: [
          { value: 0.572, itemStyle: { color: accent } },
          { value: 0.001, itemStyle: { color: accent2 } },
          { value: 0.03, itemStyle: { color: accent2, opacity: 0.55 } }
        ]
      }]
    });
    window.addEventListener('resize', function () { m.resize(); });
  }
})();
