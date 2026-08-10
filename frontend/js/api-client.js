/** ChemAI 前端 API 客户端 — fetch 封装 + KaTeX 渲染 + 共享 UI 工具
 *
 * 依赖: auth.js (ChemAuth.getToken, ChemAuth.redirectToLogin)
 *        KaTeX CDN (katex.min.js + mhchem extension)
 *
 * 用法: <script src="../../js/auth.js"></script>
 *       <script src="../../js/api-client.js"></script>
 */

// 全局快捷函数（所有页面自动可用）
var $ = function(id) { return document.getElementById(id); };

var ChemAPI = (function () {
  'use strict';

  var BASE_URL = '/api/v1';
  // ══════════════════════════════════════════════════════════════
  // HTTP 封装
  // ══════════════════════════════════════════════════════════════

  /** GET 请求
   * @param {string} url — 相对路径 (e.g. "/practice/student/1/tasks")
   * @param {object} params — 可选 query 参数
   * @returns {Promise<object>} — JSON 响应
   */
  function apiGet(url, params) {
    var fullUrl = BASE_URL + url;
    if (params) {
      var qs = Object.keys(params)
        .filter(function (k) { return params[k] !== null && params[k] !== undefined; })
        .map(function (k) { return encodeURIComponent(k) + '=' + encodeURIComponent(params[k]); })
        .join('&');
      if (qs) fullUrl += '?' + qs;
    }
    return _request(fullUrl, { method: 'GET' });
  }

  /** POST 请求
   * @param {string} url — 相对路径
   * @param {object} body — JSON 请求体
   * @returns {Promise<object>} — JSON 响应
   */
  function apiPost(url, body) {
    return _request(BASE_URL + url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  /** PATCH 请求
   * @param {string} url — 相对路径
   * @param {object} body — JSON 请求体
   * @returns {Promise<object>} — JSON 响应
   */
  function apiPatch(url, body) {
    return _request(BASE_URL + url, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  // ══════════════════════════════════════════════════════════════
  // 内部请求函数
  // ══════════════════════════════════════════════════════════════

  function _request(fullUrl, opts) {
    var token = ChemAuth.getToken();
    var headers = opts.headers || {};
    if (token) {
      headers['Authorization'] = 'Bearer ' + token;
    }
    opts.headers = headers;

    return fetch(fullUrl, opts).then(function (res) {
      // 401 → 清除 token 跳转登录
      if (res.status === 401) {
        ChemAuth.redirectToLogin();
        throw new Error('未登录或登录已过期');
      }

      // 解析 JSON 响应体
      return res.json().then(function (data) {
        if (!res.ok) {
          // 统一提取 error_code + message
          var errDetail = (data && data.detail) ? data.detail : null;
          var errorCode = errDetail ? errDetail.error_code : 'UNKNOWN';
          var message = errDetail ? (errDetail.message || errDetail.detail || '请求失败') : (data.message || '请求失败');
          var err = new Error(message);
          err.status = res.status;
          err.errorCode = errorCode;
          throw err;
        }
        return data;
      });
    });
  }

  // ══════════════════════════════════════════════════════════════
  // KaTeX 渲染
  // ══════════════════════════════════════════════════════════════

  /** 渲染容器内的所有 $...$ 和 $$...$$ LaTeX 公式
   *
   * 前提: KaTeX + mhchem CDN 已加载
   *   <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16/dist/katex.min.css">
   *   <script src="https://cdn.jsdelivr.net/npm/katex@0.16/dist/katex.min.js"><\/script>
   *   <script src="https://cdn.jsdelivr.net/npm/katex@0.16/dist/contrib/mhchem.min.js"><\/script>
   *
   * @param {HTMLElement} containerEl — 要渲染的 DOM 容器
   */
  function renderLatex(containerEl) {
    if (!containerEl) return;
    if (typeof katex === 'undefined') return; // 降级: 保留原始文本

    var html = containerEl.innerHTML;

    // 1) 行内公式 $...$ (不匹配 $$)
    html = html.replace(/(?<!\$)\$(?!\$)([^$]+?)\$(?!\$)/g, function (match, formula) {
      try {
        return katex.renderToString(formula.trim(), {
          throwOnError: false,
          strict: false,
        });
      } catch (e) {
        return match; // 渲染失败时保留原文
      }
    });

    // 2) 块级公式 $$...$$
    html = html.replace(/\$\$([^$]+?)\$\$/g, function (match, formula) {
      try {
        return katex.renderToString(formula.trim(), {
          throwOnError: false,
          strict: false,
          displayMode: true,
        });
      } catch (e) {
        return match;
      }
    });

    containerEl.innerHTML = html;
  }

  // ══════════════════════════════════════════════════════════════
  // 共享 UI 工具
  // ══════════════════════════════════════════════════════════════

  var _toastTimer;

  /** 显示 Toast 提示
   * @param {string} msg — 提示文字
   * @param {number} duration — 显示时长 ms（默认 2500）
   */
  function showToast(msg, duration) {
    var toast = document.getElementById('toast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'toast';
      toast.className = 'toast';
      document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.classList.add('show');
    clearTimeout(_toastTimer);
    _toastTimer = setTimeout(function() {
      toast.classList.remove('show');
    }, duration || 2500);
  }

  /** HTML 转义
   * @param {string} str
   * @returns {string}
   */
  function escapeHtml(str) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }

  /** 渲染选择题选项 HTML（供页面拼接用）
   * @param {Array|Object} options — 选项列表或 {A:..., B:...} 映射
   * @param {number} questionId — 题目 ID
   * @param {string} selectedAnswer — 当前选中答案字母
   * @param {string} selectFnName — 点击回调的全局函数名
   * @returns {string} HTML
   */
  function renderOptionsHtml(options, questionId, selectedAnswer, selectFnName) {
    var html = '';
    var letters = ['A', 'B', 'C', 'D', 'E', 'F'];

    if (Array.isArray(options)) {
      options.forEach(function(opt, idx) {
        var letter = letters[idx] || '';
        var isSelected = selectedAnswer === letter;
        html += '<button class="option-btn' + (isSelected ? ' selected' : '') + '" onclick="' + selectFnName + '(' + questionId + ', \'' + letter + '\')">'
          + '<span class="opt-letter">' + letter + '</span>'
          + '<span>' + (typeof opt === 'string' ? opt : (opt.label || opt.text || '')) + '</span>'
          + '</button>';
      });
    } else if (typeof options === 'object') {
      Object.keys(options).forEach(function(letter) {
        var isSelected = selectedAnswer === letter;
        html += '<button class="option-btn' + (isSelected ? ' selected' : '') + '" onclick="' + selectFnName + '(' + questionId + ', \'' + letter + '\')">'
          + '<span class="opt-letter">' + letter + '</span>'
          + '<span>' + options[letter] + '</span>'
          + '</button>';
      });
    }
    return html;
  }

  /** 创建逐题导航器（goPrev / goNext）
   * @param {object} state — { currentQIndex, ... }
   * @param {function} renderFn — 重渲染回调
   * @param {string} arrayProp — 题目数组在 state 中的属性名（默认 "questions"）
   * @returns {{ goPrev: function, goNext: function }}
   */
  function createQuizNavigator(state, renderFn, arrayProp) {
    var prop = arrayProp || 'questions';
    return {
      goPrev: function() {
        if (state.currentQIndex > 0) {
          state.currentQIndex--;
          renderFn();
        }
      },
      goNext: function() {
        if (state.currentQIndex < state[prop].length - 1) {
          state.currentQIndex++;
          renderFn();
        }
      },
    };
  }

  /** 更新底部导航按钮状态
   * @param {string} btnPrevId — "上一题" 按钮 ID
   * @param {string} btnNextId — "下一题/提交" 按钮 ID
   * @param {number} currentIndex — 当前题索引
   * @param {number} totalCount — 总题数
   * @param {function} onSubmit — 提交回调
   * @param {function} onNext — 下一题回调
   */
  function updateQuizNav(btnPrevId, btnNextId, currentIndex, totalCount, onSubmit, onNext) {
    var prev = document.getElementById(btnPrevId);
    var next = document.getElementById(btnNextId);
    if (prev) prev.disabled = currentIndex === 0;
    if (!next) return;
    var isLast = currentIndex >= totalCount - 1;
    if (isLast) {
      next.textContent = '提交';
      next.className = 'btn-nav submit';
      next.onclick = onSubmit;
    } else {
      next.textContent = '下一题 →';
      next.className = 'btn-nav next';
      next.onclick = onNext;
    }
  }

  /** 验证 6 位数字绑定码格式
   * @param {string} code — 绑定码字符串
   * @returns {boolean} — 是否为有效 6 位数字
   */
  function validateBindCode(code) {
    return /^\d{6}$/.test(code);
  }

  // ── 化学术语 → 通俗表述（家长端前端兜底）────────────────────
  var _TERM_MAP = {
    "氧化还原反应": "与电子转移相关的反应",
    "离子反应": "溶液中离子的反应",
    "物质的量": "化学计量单位",
    "摩尔": "化学计量单位",
    "化学平衡": "反应的动态平衡",
    "元素周期律": "元素性质的规律",
    "电解质": "能导电的化合物",
    "共价键": "原子间的连接方式",
    "离子键": "原子间的连接方式",
    "配平": "方程式配平",
    "沉淀": "不溶于水的固体",
    "中和反应": "酸碱反应",
    "摩尔质量": "单位物质的量的质量",
    "阿伏加德罗常数": "微观粒子计数单位",
    "电离": "物质在水中分解",
    "水解": "物质与水的反应",
    "酯化反应": "酸与醇生成酯的反应",
    "加成反应": "有机物加成的反应",
    "取代反应": "有机物原子替换的反应",
    "消去反应": "有机物消除小分子的反应",
  };

  /** 将化学专业术语替换为通俗表述（家长端前端兜底）。
   * 后端已做转换，此函数作为客户端防御层，确保未被转换的术语不会直接展示。
   * @param {string} text — 原始文本
   * @returns {string} — 替换后的文本
   */
  function convertTerms(text) {
    if (!text) return text;
    var result = text;
    Object.keys(_TERM_MAP).forEach(function(term) {
      if (result.indexOf(term) !== -1) {
        result = result.split(term).join(_TERM_MAP[term]);
      }
    });
    return result;
  }

  // ══════════════════════════════════════════════════════════════

  return {
    apiGet: apiGet,
    apiPost: apiPost,
    apiPatch: apiPatch,
    renderLatex: renderLatex,
    showToast: showToast,
    escapeHtml: escapeHtml,
    renderOptionsHtml: renderOptionsHtml,
    createQuizNavigator: createQuizNavigator,
    updateQuizNav: updateQuizNav,
    validateBindCode: validateBindCode,
    convertTerms: convertTerms,
    BASE_URL: BASE_URL,
  };
})();
