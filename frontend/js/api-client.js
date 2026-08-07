/** ChemAI 前端 API 客户端 — fetch 封装 + KaTeX 渲染
 *
 * 依赖: auth.js (ChemAuth.getToken, ChemAuth.redirectToLogin)
 *        KaTeX CDN (katex.min.js + mhchem extension)
 *
 * 用法: <script src="../../js/auth.js"></script>
 *       <script src="../../js/api-client.js"></script>
 */

var ChemAPI = (function () {
  'use strict';

  var BASE_URL = '/api/v1';
  // 默认每页条数
  var DEFAULT_LIMIT = 20;

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
          var message = errDetail ? errDetail.message : (data.message || '请求失败');
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

  return {
    apiGet: apiGet,
    apiPost: apiPost,
    renderLatex: renderLatex,
    BASE_URL: BASE_URL,
    DEFAULT_LIMIT: DEFAULT_LIMIT,
  };
})();
