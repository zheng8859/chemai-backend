/** ChemAI 前端认证模块 — JWT token 存取 + 用户信息解码
 *
 * JWT payload: { user_id, role, school_id?, sub_role?, type, iat, exp }
 * 后端: app/core/security.py create_access_token()
 *
 * 用法: <script src="../../js/auth.js"></script>
 */

var ChemAuth = (function () {
  'use strict';

  var TOKEN_KEY = 'chemai_token';
  var LOGIN_PAGE = 'login.html';

  // ══════════════════════════════════════════════════════════════
  // Token 存取
  // ══════════════════════════════════════════════════════════════

  function getToken() {
    return localStorage.getItem(TOKEN_KEY);
  }

  function setToken(token) {
    localStorage.setItem(TOKEN_KEY, token);
  }

  function clearToken() {
    localStorage.removeItem(TOKEN_KEY);
  }

  // ══════════════════════════════════════════════════════════════
  // JWT 解码 (无依赖, base64url decode)
  // ══════════════════════════════════════════════════════════════

  function decodeToken(token) {
    if (!token) return null;
    try {
      var parts = token.split('.');
      if (parts.length !== 3) return null;
      // base64url → base64 → decode
      var payload = parts[1].replace(/-/g, '+').replace(/_/g, '/');
      // pad to multiple of 4
      while (payload.length % 4) payload += '=';
      return JSON.parse(atob(payload));
    } catch (e) {
      return null;
    }
  }

  // ══════════════════════════════════════════════════════════════
  // 用户信息
  // ══════════════════════════════════════════════════════════════

  function getCurrentUser() {
    var payload = decodeToken(getToken());
    if (!payload) return null;
    // 检查过期
    if (payload.exp && payload.exp * 1000 < Date.now()) {
      clearToken();
      return null;
    }
    return {
      userId: payload.user_id,
      role: payload.role,
      schoolId: payload.school_id || null,
      subRole: payload.sub_role || null,
    };
  }

  function getUserId() {
    var user = getCurrentUser();
    return user ? user.userId : null;
  }

  function getUserRole() {
    var user = getCurrentUser();
    return user ? user.role : null;
  }

  function isAuthenticated() {
    return getCurrentUser() !== null;
  }

  // ══════════════════════════════════════════════════════════════
  // 导航
  // ══════════════════════════════════════════════════════════════

  function redirectToLogin() {
    clearToken();
    // 检测当前页在哪一层，构建正确的 login 路径
    var path = window.location.pathname;
    var prefix = '';
    if (path.indexOf('/pages/m/') !== -1) {
      prefix = '';
    } else if (path.indexOf('/pages/') !== -1) {
      prefix = '';
    } else {
      prefix = 'pages/m/';
    }
    window.location.href = prefix + LOGIN_PAGE;
  }

  // ══════════════════════════════════════════════════════════════
  // 登录后保存 (供 login.html 调用)
  // ══════════════════════════════════════════════════════════════

  function login(token) {
    setToken(token);
    // 根据角色跳转
    var user = decodeToken(token);
    if (user && user.role === 'teacher' || user && user.role === 'system_admin') {
      window.location.href = '../teacher.html';
    } else if (user && user.role === 'parent') {
      window.location.href = 'parent.html';
    } else {
      window.location.href = 'index.html';
    }
  }

  // ══════════════════════════════════════════════════════════════

  return {
    getToken: getToken,
    setToken: setToken,
    clearToken: clearToken,
    decodeToken: decodeToken,
    getCurrentUser: getCurrentUser,
    getUserId: getUserId,
    getUserRole: getUserRole,
    isAuthenticated: isAuthenticated,
    redirectToLogin: redirectToLogin,
    login: login,
    TOKEN_KEY: TOKEN_KEY,
  };
})();
