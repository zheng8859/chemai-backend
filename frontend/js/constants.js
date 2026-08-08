/** ChemAI 前端常量 — 预警类型/严重度标签映射
 *
 * 依赖: 无
 *
 * 用法: <script src="../../js/constants.js"></script>
 */

var ChemConst = (function () {
  'use strict';

  // ══════════════════════════════════════════════════════════════
  // 预警类型 → 中文标签 + 颜色
  // ══════════════════════════════════════════════════════════════

  var WARNING_TYPE_LABELS = {
    consecutive_absence: '未登录',
    score_drop: '成绩下滑',
    high_error_rate: '高错误率',
    new_barrier: '障碍迁移',
  };

  var WARNING_TYPE_COLORS = {
    consecutive_absence: '#6b7280',
    score_drop: '#f97316',
    high_error_rate: '#ef4444',
    new_barrier: '#7c3aed',
  };

  // ══════════════════════════════════════════════════════════════
  // 预警严重度 → 中文标签 + 颜色
  // ══════════════════════════════════════════════════════════════

  var WARNING_SEVERITY_LABELS = {
    info: '提示',
    warning: '警告',
    severe: '严重',
  };

  var WARNING_SEVERITY_COLORS = {
    info: '#3b82f6',
    warning: '#f59e0b',
    severe: '#ef4444',
  };

  // ══════════════════════════════════════════════════════════════
  // 预警状态 → 中文标签
  // ══════════════════════════════════════════════════════════════

  var WARNING_STATUS_LABELS = {
    pending: '待处理',
    processing: '处理中',
    resolved: '已解决',
    dismissed: '已忽略',
  };

  // ══════════════════════════════════════════════════════════════
  // 障碍类型 → 中文标签 + 颜色
  // ══════════════════════════════════════════════════════════════

  var BARRIER_LABELS = {
    concept: '概念理解',
    reading: '审题障碍',
    expression: '表述障碍',
  };

  var BARRIER_COLORS = {
    concept: '#7c3aed',
    reading: '#2563eb',
    expression: '#06b6d4',
  };

  // ══════════════════════════════════════════════════════════════
  // 工具函数
  // ══════════════════════════════════════════════════════════════

  function warningTypeLabel(type) {
    return WARNING_TYPE_LABELS[type] || type || '未知';
  }

  function warningTypeColor(type) {
    return WARNING_TYPE_COLORS[type] || '#6b7280';
  }

  function warningSeverityLabel(severity) {
    return WARNING_SEVERITY_LABELS[severity] || severity || '未知';
  }

  function warningSeverityColor(severity) {
    return WARNING_SEVERITY_COLORS[severity] || '#6b7280';
  }

  function warningStatusLabel(status) {
    return WARNING_STATUS_LABELS[status] || status || '未知';
  }

  function barrierLabel(type) {
    return BARRIER_LABELS[type] || type || '未知';
  }

  function barrierColor(type) {
    return BARRIER_COLORS[type] || '#6b7280';
  }

  // ══════════════════════════════════════════════════════════════

  return {
    WARNING_TYPE_LABELS: WARNING_TYPE_LABELS,
    WARNING_TYPE_COLORS: WARNING_TYPE_COLORS,
    WARNING_SEVERITY_LABELS: WARNING_SEVERITY_LABELS,
    WARNING_SEVERITY_COLORS: WARNING_SEVERITY_COLORS,
    WARNING_STATUS_LABELS: WARNING_STATUS_LABELS,
    BARRIER_LABELS: BARRIER_LABELS,
    BARRIER_COLORS: BARRIER_COLORS,
    warningTypeLabel: warningTypeLabel,
    warningTypeColor: warningTypeColor,
    warningSeverityLabel: warningSeverityLabel,
    warningSeverityColor: warningSeverityColor,
    warningStatusLabel: warningStatusLabel,
    barrierLabel: barrierLabel,
    barrierColor: barrierColor,
  };
})();
