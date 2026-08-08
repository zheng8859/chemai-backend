/** ChemAI 前端图表工具 — 零依赖 SVG 折线图渲染
 *
 * 依赖: 无外部库，纯 Vanilla JS + SVG DOM
 *
 * 用法: <script src="../../js/charts.js"></script>
 *       Charts.renderTrendChart('chart-container', data, options);
 */

var Charts = (function () {
  'use strict';

  // ══════════════════════════════════════════════════════════════
  // 默认配置
  // ══════════════════════════════════════════════════════════════

  var DEFAULTS = {
    width: 660,
    height: 260,
    padding: { top: 12, right: 12, bottom: 40, left: 52 },
    lineColor: '#002045',
    dotColor: '#002045',
    dotRadius: 4,
    gridColor: '#e5e5e5',
    gridDash: '4,4',
    labelColor: '#888888',
    yMin: 60,
    yMax: 90,
    yStep: 10,
  };

  // ══════════════════════════════════════════════════════════════
  // SVG 折线图渲染
  // ══════════════════════════════════════════════════════════════

  /**
   * 在指定容器内渲染 SVG 折线图
   *
   * @param {string|HTMLElement} container — 容器 ID 或 DOM 元素
   * @param {Array} data — [{label: string, value: number|null}, ...]
   * @param {Object} options — 可选覆盖默认配置
   */
  function renderTrendChart(container, data, options) {
    var el = typeof container === 'string'
      ? document.getElementById(container)
      : container;
    if (!el) return;

    var opts = _mergeOptions(options || {});

    // 过滤有效数据点
    var points = [];
    for (var i = 0; i < data.length; i++) {
      if (data[i] && data[i].value !== null && data[i].value !== undefined) {
        points.push(data[i]);
      }
    }

    // 空数据兜底
    if (points.length === 0) {
      el.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:' + opts.height + 'px;color:#888;font-size:14px;">暂无考试数据</div>';
      return;
    }

    var W = opts.width;
    var H = opts.height;
    var pad = opts.padding;
    var plotW = W - pad.left - pad.right;
    var plotH = H - pad.top - pad.bottom;
    var yRange = opts.yMax - opts.yMin;

    // 计算坐标
    var coords = [];
    for (var i = 0; i < points.length; i++) {
      var x = pad.left + (points.length === 1 ? plotW / 2 : (i / (points.length - 1)) * plotW);
      var yVal = Math.max(opts.yMin, Math.min(opts.yMax, points[i].value));
      var y = pad.top + plotH - ((yVal - opts.yMin) / yRange) * plotH;
      coords.push({ x: x, y: y, label: points[i].label, value: points[i].value });
    }

    // 构建 SVG
    var svg = _createSvg(W, H);

    // 网格线 + Y 轴标签
    for (var v = opts.yMin; v <= opts.yMax; v += opts.yStep) {
      var gy = pad.top + plotH - ((v - opts.yMin) / yRange) * plotH;
      svg.appendChild(_createLine(pad.left, gy, W - pad.right, gy, opts.gridColor, opts.gridDash));
      svg.appendChild(_createText(pad.left - 6, gy + 4, String(v), opts.labelColor, 'end'));
    }

    // 折线
    if (points.length >= 2) {
      var polyline = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
      var ptsStr = coords.map(function (c) { return c.x + ',' + c.y; }).join(' ');
      polyline.setAttribute('points', ptsStr);
      polyline.setAttribute('fill', 'none');
      polyline.setAttribute('stroke', opts.lineColor);
      polyline.setAttribute('stroke-width', '2');
      polyline.setAttribute('stroke-linecap', 'round');
      polyline.setAttribute('stroke-linejoin', 'round');
      svg.appendChild(polyline);

      // 填充区域
      var firstX = coords[0].x;
      var lastX = coords[coords.length - 1].x;
      var bottomY = pad.top + plotH;
      var areaPts = firstX + ',' + bottomY + ' ' + coords.map(function (c) { return c.x + ',' + c.y; }).join(' ') + ' ' + lastX + ',' + bottomY;
      var area = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
      area.setAttribute('points', areaPts);
      area.setAttribute('fill', opts.lineColor);
      area.setAttribute('opacity', '0.08');
      svg.appendChild(area);
    }

    // 数据点
    for (var j = 0; j < coords.length; j++) {
      var circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      circle.setAttribute('cx', coords[j].x);
      circle.setAttribute('cy', coords[j].y);
      circle.setAttribute('r', opts.dotRadius);
      circle.setAttribute('fill', opts.dotColor);
      circle.setAttribute('stroke', '#fff');
      circle.setAttribute('stroke-width', '2');
      svg.appendChild(circle);
    }

    // X 轴标签
    for (var k = 0; k < coords.length; k++) {
      svg.appendChild(_createText(coords[k].x, pad.top + plotH + 20, coords[k].label, opts.labelColor, 'middle'));
    }

    el.innerHTML = '';
    el.appendChild(svg);
  }

  // ══════════════════════════════════════════════════════════════
  // SVG 元素工厂
  // ══════════════════════════════════════════════════════════════

  function _createSvg(w, h) {
    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
    svg.setAttribute('width', '100%');
    svg.setAttribute('height', h);
    svg.style.display = 'block';
    return svg;
  }

  function _createLine(x1, y1, x2, y2, color, dash) {
    var line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', x1);
    line.setAttribute('y1', y1);
    line.setAttribute('x2', x2);
    line.setAttribute('y2', y2);
    line.setAttribute('stroke', color);
    line.setAttribute('stroke-width', '1');
    if (dash) line.setAttribute('stroke-dasharray', dash);
    return line;
  }

  function _createText(x, y, text, color, anchor) {
    var t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    t.setAttribute('x', x);
    t.setAttribute('y', y);
    t.setAttribute('fill', color);
    t.setAttribute('font-size', '11');
    t.setAttribute('font-family', 'IBM Plex Sans, sans-serif');
    t.setAttribute('text-anchor', anchor || 'start');
    t.textContent = text;
    return t;
  }

  // ══════════════════════════════════════════════════════════════
  // 配置合并
  // ══════════════════════════════════════════════════════════════

  function _mergeOptions(userOpts) {
    var merged = {};
    var keys = Object.keys(DEFAULTS);
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i];
      if (userOpts.hasOwnProperty(k)) {
        // 嵌套对象浅合并
        if (typeof DEFAULTS[k] === 'object' && !Array.isArray(DEFAULTS[k])) {
          merged[k] = _shallowMerge(DEFAULTS[k], userOpts[k] || {});
        } else {
          merged[k] = userOpts[k];
        }
      } else {
        merged[k] = DEFAULTS[k];
      }
    }
    return merged;
  }

  function _shallowMerge(base, override) {
    var r = {};
    var bk = Object.keys(base);
    for (var i = 0; i < bk.length; i++) { r[bk[i]] = base[bk[i]]; }
    var ok = Object.keys(override);
    for (var j = 0; j < ok.length; j++) { r[ok[j]] = override[ok[j]]; }
    return r;
  }

  // ══════════════════════════════════════════════════════════════

  return {
    renderTrendChart: renderTrendChart,
  };
})();
