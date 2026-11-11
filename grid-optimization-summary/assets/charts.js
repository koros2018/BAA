// assets/charts.js — 网格索引优化技术总结报告图表
(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();

  // --- Chart: 主要瓶颈步骤优化前后耗时对比（对数坐标） ---
  var perfEl = document.getElementById('chart-perf');
  if (perfEl) {
    var perf = echarts.init(perfEl, null, { renderer: 'svg' });
    perf.setOption({
      animation: false,
      tooltip: {
        trigger: 'axis',
        appendToBody: true,
        formatter: function(params) {
          var s = params[0].name + '<br/>';
          params.forEach(function(p) {
            s += p.marker + p.seriesName + ': <b>' + p.value + 's</b><br/>';
          });
          return s;
        }
      },
      legend: { textStyle: { color: muted }, top: 0 },
      grid: { left: 60, right: 30, top: 40, bottom: 40 },
      xAxis: {
        type: 'category',
        data: ['_bind_dimensions', '_sweep_line', '_build_relations', '_infer_room_types', '_classify_entities'],
        axisLabel: { color: muted, fontSize: 11, interval: 0, rotate: 15 },
        axisLine: { lineStyle: { color: rule } }
      },
      yAxis: {
        type: 'log',
        name: '耗时（秒，对数）',
        nameTextStyle: { color: muted },
        axisLabel: { color: muted },
        axisLine: { lineStyle: { color: rule } },
        splitLine: { lineStyle: { color: rule, opacity: 0.5 } }
      },
      series: [
        {
          name: '优化前',
          type: 'bar',
          data: [34.52, 2.38, 1.24, 0.37, 0.31],
          itemStyle: { color: accent + '66', borderRadius: [4, 4, 0, 0] },
          barMaxWidth: 40
        },
        {
          name: '优化后',
          type: 'bar',
          data: [0.064, 0.033, 0.047, 0.010, 0.132],
          itemStyle: { color: accent2, borderRadius: [4, 4, 0, 0] },
          barMaxWidth: 40
        }
      ]
    });
    window.addEventListener('resize', function() { perf.resize(); });
  }

  // --- Chart: 语义分析总耗时随优化阶段递减 ---
  var totalEl = document.getElementById('chart-total');
  if (totalEl) {
    var total = echarts.init(totalEl, null, { renderer: 'svg' });
    total.setOption({
      animation: false,
      tooltip: {
        trigger: 'axis',
        appendToBody: true,
        formatter: function(params) {
          var p = params[0];
          return p.name + '<br/>总耗时: <b>' + p.value + 's</b>';
        }
      },
      grid: { left: 60, right: 30, top: 30, bottom: 40 },
      xAxis: {
        type: 'category',
        data: ['基线', 'P0-2\nsweep', 'P0-3\nrelations', 'P0-4\nclassify', 'P0-5\ntable', 'P0-6\ntext', 'P0-7\nfloor', 'P0-8\nfinal'],
        axisLabel: { color: muted, fontSize: 10, interval: 0 },
        axisLine: { lineStyle: { color: rule } }
      },
      yAxis: {
        type: 'value',
        name: '总耗时（秒）',
        nameTextStyle: { color: muted },
        axisLabel: { color: muted },
        axisLine: { lineStyle: { color: rule } },
        splitLine: { lineStyle: { color: rule, opacity: 0.5 } }
      },
      series: [{
        name: '总耗时',
        type: 'line',
        smooth: true,
        symbolSize: 8,
        data: [6.96, 2.21, 0.79, 0.63, 0.567, 0.495, 0.47, 0.425],
        lineStyle: { color: accent, width: 3 },
        itemStyle: { color: accent },
        areaStyle: { color: {
          type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: accent + '44' }, { offset: 1, color: accent + '00' }]
        } },
        label: { show: true, color: ink, fontSize: 10, formatter: function(p) { return p.value.toFixed(2) + 's'; } }
      }]
    });
    window.addEventListener('resize', function() { total.resize(); });
  }
})();
