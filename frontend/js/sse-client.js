/** ChemAI SSE 客户端 — Agent 流式对话引擎
 *
 * 依赖: auth.js (ChemAuth.getToken)
 *
 * 用法: <script src="../../js/auth.js"></script>
 *       <script src="../../js/sse-client.js"></script>
 */

var ChemSSE = (function () {
  'use strict';

  // ══════════════════════════════════════════════════════════════
  // 状态机
  // ══════════════════════════════════════════════════════════════

  var _state = 'idle';       // idle | connecting | streaming | done | error
  var _controller = null;    // AbortController 实例
  var _sending = false;      // 发送锁

  /** 重置内部状态 */
  function _reset() {
    _state = 'idle';
    _controller = null;
    _sending = false;
  }

  // ══════════════════════════════════════════════════════════════
  // SSE 帧解析器
  // ══════════════════════════════════════════════════════════════

  /**
   * 解析原始 SSE 文本块，拆分为事件对象数组
   * 按 \n\n 分割帧，提取 event: 和 data: 字段
   *
   * @param {string} chunk — 原始 SSE 文本块
   * @returns {Array<{event: string, data: string}>}
   */
  function parseChunk(chunk) {
    var events = [];
    var parts = chunk.split('\n\n');

    for (var i = 0; i < parts.length; i++) {
      var frame = parts[i].trim();
      if (!frame) continue;

      var eventType = 'message'; // SSE 默认事件类型
      var dataLines = [];

      var lines = frame.split('\n');
      for (var j = 0; j < lines.length; j++) {
        var line = lines[j];
        if (line.indexOf('event:') === 0) {
          eventType = line.substring(6).trim();
        } else if (line.indexOf('data:') === 0) {
          dataLines.push(line.substring(5).trim());
        }
      }

      if (dataLines.length > 0) {
        events.push({
          event: eventType,
          data: dataLines.join('\n'),
        });
      }
    }

    return events;
  }

  // ══════════════════════════════════════════════════════════════
  // 核心连接方法
  // ══════════════════════════════════════════════════════════════

  /**
   * 建立 SSE 连接并流式处理事件
   *
   * @param {string} url — SSE 端点路径 (e.g. "/api/v1/chat/stream")
   * @param {object} body — POST 请求体 {message, thread_id, context}
   * @param {object} handlers — 事件处理器映射 {phase, text, tool_call, ...}
   * @returns {object} {abort: function} — 返回取消函数供外部调用
   */
  function connect(url, body, handlers) {
    // 发送锁：防止重复发送
    if (_sending) {
      console.warn('[ChemSSE] 发送锁激活，忽略重复请求');
      return { abort: function () {} };
    }

    _sending = true;
    _state = 'connecting';
    _controller = new AbortController();
    handlers = handlers || {};

    // 注入 Bearer token
    var token = (typeof ChemAuth !== 'undefined') ? ChemAuth.getToken() : null;
    var headers = {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
    };
    if (token) {
      headers['Authorization'] = 'Bearer ' + token;
    }

    fetch(url, {
      method: 'POST',
      headers: headers,
      body: JSON.stringify(body),
      signal: _controller.signal,
    }).then(function (response) {
      if (!response.ok) {
        // HTTP 错误 (401 / 500 等)
        _state = 'error';
        _sending = false;
        // 401 → 清除 token 跳转登录（与 api-client.js 行为一致）
        if (response.status === 401 && typeof ChemAuth !== 'undefined') {
          ChemAuth.redirectToLogin();
          return;
        }
        if (handlers.error) {
          handlers.error({
            type: 'error',
            code: 'HTTP_' + response.status,
            message: '服务器错误 (' + response.status + ')',
            recoverable: response.status >= 500,
          });
        }
        return;
      }

      _state = 'streaming';

      var reader = response.body.getReader();
      var decoder = new TextDecoder();
      var buffer = '';

      function read() {
        reader.read().then(function (result) {
          if (result.done) {
            // 流正常结束
            _state = 'done';
            _sending = false;
            _controller = null;
            if (handlers.done) {
              handlers.done({ type: 'done' });
            }
            return;
          }

          // 解码并追加到缓冲区
          buffer += decoder.decode(result.value, { stream: true });

          // 按 \n\n 分割完整帧
          var events = parseChunk(buffer);

          // 如果解析出事件，清除已消费的缓冲区
          if (events.length > 0) {
            // 保留最后一部分不完整的数据
            var lastDoubleNewline = buffer.lastIndexOf('\n\n');
            if (lastDoubleNewline !== -1) {
              buffer = buffer.substring(lastDoubleNewline + 2);
            }
          }

          // 分派事件
          for (var i = 0; i < events.length; i++) {
            var ev = events[i];
            _dispatch(ev.event, ev.data, handlers);
          }

          // 继续读取
          read();
        }).catch(function (err) {
          if (err.name === 'AbortError') {
            // 用户主动取消，静默处理
            _reset();
            return;
          }

          // 网络错误
          _state = 'error';
          _sending = false;
          _controller = null;

          if (handlers.error) {
            handlers.error({
              type: 'error',
              code: 'NETWORK_ERROR',
              message: '网络连接失败，请重试',
              recoverable: true,
            });
          }
        });
      }

      read();
    }).catch(function (err) {
      if (err.name === 'AbortError') {
        _reset();
        return;
      }

      _state = 'error';
      _sending = false;
      _controller = null;

      if (handlers.error) {
        handlers.error({
          type: 'error',
          code: 'FETCH_ERROR',
          message: '网络连接失败，请重试',
          recoverable: true,
        });
      }
    });

    return { abort: abort };
  }

  // ══════════════════════════════════════════════════════════════
  // 事件分派
  // ══════════════════════════════════════════════════════════════

  function _dispatch(eventType, rawData, handlers) {
    // 解析 JSON data
    var data = rawData;
    try {
      data = JSON.parse(rawData);
    } catch (e) {
      // 非 JSON 数据保持原字符串
    }

    // 内置事件处理
    switch (eventType) {
      case 'navigate':
        _handleNavigate(data);
        break;
    }

    // 调用用户注册的 handler
    var handler = handlers[eventType];
    if (typeof handler === 'function') {
      handler(data);
    } else if (handlers['*']) {
      // 通配符 handler：捕获所有事件
      handlers['*'](eventType, data);
    }
  }

  /** 内置 navigate 处理：页面跳转 */
  function _handleNavigate(data) {
    if (data && data.page) {
      var url = data.page;
      // 自动补 .html 后缀
      if (url.indexOf('.html') === -1 && url.indexOf('http') !== 0) {
        url += '.html';
      }
      // 携带 query 参数
      if (data.params && typeof data.params === 'object') {
        var qs = Object.keys(data.params)
          .map(function (k) { return encodeURIComponent(k) + '=' + encodeURIComponent(data.params[k]); })
          .join('&');
        if (qs) url += '?' + qs;
      }
      setTimeout(function () {
        location.href = url;
      }, 200);
    }
  }

  // ══════════════════════════════════════════════════════════════
  // 公共方法
  // ══════════════════════════════════════════════════════════════

  /** 取消当前 SSE 连接 */
  function abort() {
    if (_controller) {
      _controller.abort();
      _reset();
    }
  }

  /** 获取当前连接状态 */
  function getState() {
    return _state;
  }

  /** 是否正在发送 */
  function isSending() {
    return _sending;
  }

  // ══════════════════════════════════════════════════════════════

  return {
    connect: connect,
    abort: abort,
    getState: getState,
    isSending: isSending,
    parseChunk: parseChunk, // 暴露供测试
  };
})();
