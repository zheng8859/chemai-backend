/** ChemAI Agent 渲染器 — SSE tool_result 的富 HTML 渲染
 *
 * 依赖: api-client.js (ChemAPI.escapeHtml)
 *
 * 用法: <script src="../../js/api-client.js"></script>
 *       <script src="../../js/agent-renderer.js"></script>
 */

var ChemAgentRender = (function () {
  'use strict';

  // ══════════════════════════════════════════════════════════════
  // 工具中文名映射
  // ══════════════════════════════════════════════════════════════

  var TOOL_NAMES = {
    chemistry_tutor: '化学辅导',
    ionic_equation_tutor: '离子方程式辅导',
    stoichiometry_tutor: '化学计量辅导',
    redox_tutor: '氧化还原辅导',
    equilibrium_tutor: '化学平衡辅导',
    periodic_law_tutor: '周期律辅导',
    organic_tutor: '有机推断辅导',
    simulate_experiment: '模拟实验',
    web_search: '联网搜索',
  };

  /** 获取工具中文名 */
  function toolLabel(name) {
    return TOOL_NAMES[name] || name;
  }

  // ══════════════════════════════════════════════════════════════
  // 工具卡片外壳
  // ══════════════════════════════════════════════════════════════

  /**
   * 生成工具结果卡片 HTML
   * @param {string} toolName — 工具名
   * @param {string} innerHtml — 卡片内容 HTML
   * @param {string} icon — 图标 emoji（默认 ⚡）
   */
  function _card(toolName, innerHtml, icon) {
    var label = toolLabel(toolName);
    var ico = icon || '⚡';
    return (
      '<div class="tool-card">'
      + '<div class="tool-card-header">'
      + '<span class="tool-card-icon">' + ico + '</span>'
      + '<span class="tool-card-title">' + label + '</span>'
      + '</div>'
      + '<div class="tool-card-body">' + innerHtml + '</div>'
      + '</div>'
    );
  }

  // ══════════════════════════════════════════════════════════════
  // 7 个 Student 工具渲染器
  // ══════════════════════════════════════════════════════════════

  /**
   * chemistry_tutor — 通用辅导文本
   * 输出自然语言辅导文本，支持 LaTeX
   */
  function _renderChemistryTutor(result) {
    var text = _extractText(result);
    return _card('chemistry_tutor', '<div class="tutor-text">' + _escapeLatex(text) + '</div>', '📖');
  }

  /**
   * ionic_equation_tutor — 苏格拉底四步法
   * Step 1: 判断可拆物质 → Step 2: 写成离子 → Step 3: 删不变离子 → Step 4: 检查守恒
   */
  function _renderIonicEquationTutor(result) {
    var steps = [
      { num: '1', title: '判断可拆物质', desc: '强酸、强碱、可溶盐拆为离子；弱电解质、沉淀、气体、氧化物保留化学式', icon: '🔍' },
      { num: '2', title: '写成离子形式', desc: '将拆开的物质写成离子，未拆的保留化学式', icon: '✏️' },
      { num: '3', title: '删去不变离子', desc: '等式两边相同的离子消去（旁观离子）', icon: '🗑️' },
      { num: '4', title: '检查守恒', desc: '确认电荷守恒 + 原子守恒', icon: '✅' },
    ];
    return _card('ionic_equation_tutor', _renderSteps(steps, result), '🧪');
  }

  /**
   * stoichiometry_tutor — 计算步骤
   * 提取已知量 → 选公式 → 列关系式 → 分步计算
   */
  function _renderStoichiometryTutor(result) {
    var steps = [
      { num: '1', title: '提取已知量', desc: '从题干中找出已知的质量/物质的量/气体体积', icon: '📋' },
      { num: '2', title: '选择公式', desc: '根据已知量和未知量选择合适的化学计量关系', icon: '📐' },
      { num: '3', title: '列出关系式', desc: '写出比例关系：n₁/ν₁ = n₂/ν₂', icon: '🔗' },
      { num: '4', title: '分步计算', desc: '代入数值，逐步求解未知量', icon: '🧮' },
    ];
    return _card('stoichiometry_tutor', _renderSteps(steps, result), '📊');
  }

  /**
   * redox_tutor — 三步法
   * 标化合价 → 找升降 → 电子守恒配平
   */
  function _renderRedoxTutor(result) {
    var steps = [
      { num: '1', title: '标化合价', desc: '标出反应前后各元素的化合价变化', icon: '🏷️' },
      { num: '2', title: '找升降', desc: '确定氧化剂（降价）和还原剂（升价），计算得失电子数', icon: '↕️' },
      { num: '3', title: '电子守恒配平', desc: '根据得失电子数相等，配平氧化剂和还原剂的系数，再配平其他原子', icon: '⚖️' },
    ];
    return _card('redox_tutor', _renderSteps(steps, result), '🔴');
  }

  /**
   * equilibrium_tutor — 三段式表格
   * 初始 → 变化 → 平衡，三行浓度数据
   */
  function _renderEquilibriumTutor(result) {
    var text = _extractText(result);
    var html = '<div class="tutor-text">' + _escapeLatex(text) + '</div>';
    // 如果结果包含三段式数据，渲染表格
    if (result && result.table_data) {
      html += _renderEquilibriumTable(result.table_data);
    }
    return _card('equilibrium_tutor', html, '⚖️');
  }

  function _renderEquilibriumTable(data) {
    var rows = data.rows || [];
    var cols = data.columns || ['', '反应物', '生成物'];
    var html = '<table class="eq-table"><thead><tr>';
    for (var c = 0; c < cols.length; c++) {
      html += '<th>' + _esc(cols[c]) + '</th>';
    }
    html += '</tr></thead><tbody>';
    var labels = ['初始', '变化', '平衡'];
    for (var r = 0; r < rows.length; r++) {
      html += '<tr><td class="eq-label">' + (labels[r] || '') + '</td>';
      var row = rows[r];
      for (var i = 0; i < row.length; i++) {
        html += '<td>' + _esc(String(row[i])) + '</td>';
      }
      html += '</tr>';
    }
    html += '</tbody></table>';
    return html;
  }

  /**
   * periodic_law_tutor — 位置→结构→性质推断
   */
  function _renderPeriodicLawTutor(result) {
    var steps = [
      { num: '1', title: '确定位置', desc: '根据原子序数确定元素在周期表中的位置（周期、族）', icon: '📍' },
      { num: '2', title: '推断结构', desc: '由位置推断原子结构：电子层数 = 周期数，最外层电子数 = 族序数', icon: '⚛️' },
      { num: '3', title: '归纳性质', desc: '根据结构和位置归纳元素性质：金属性/非金属性、原子半径、电负性等递变规律', icon: '📝' },
    ];
    return _card('periodic_law_tutor', _renderSteps(steps, result), '🔬');
  }

  /**
   * simulate_experiment — 实验报告
   * 目的 / 仪器 / 步骤 / 现象 / 方程式 / 原理 / 安全提醒 / 考点
   */
  function _renderSimulateExperiment(result) {
    var text = _extractText(result);
    // 尝试解析结构化实验报告字段
    var sections = [];
    var fields = [
      { key: 'purpose', label: '🎯 实验目的' },
      { key: 'apparatus', label: '🧰 实验仪器' },
      { key: 'procedure', label: '📋 实验步骤' },
      { key: 'phenomenon', label: '👁️ 实验现象' },
      { key: 'equation', label: '⚗️ 化学方程式' },
      { key: 'principle', label: '💡 实验原理' },
      { key: 'safety', label: '⚠️ 安全提醒' },
      { key: 'exam_points', label: '📌 常见考点' },
    ];

    var hasStructured = false;
    for (var i = 0; i < fields.length; i++) {
      var val = result ? result[fields[i].key] : null;
      if (val) {
        hasStructured = true;
        sections.push('<div class="exp-section"><div class="exp-label">' + fields[i].label + '</div><div class="exp-content">' + _escapeLatex(val) + '</div></div>');
      }
    }

    if (!hasStructured) {
      // 纯文本实验报告
      sections.push('<div class="tutor-text">' + _escapeLatex(text) + '</div>');
    }

    return _card('simulate_experiment', sections.join(''), '🔬');
  }

  // ══════════════════════════════════════════════════════════════
  // 通用兜底渲染器
  // ══════════════════════════════════════════════════════════════

  function _renderFallback(toolName, result) {
    var text = _extractText(result);
    var label = toolLabel(toolName);
    var html = '<pre class="tool-raw">' + _esc(text) + '</pre>';
    return _card(toolName, html, '🔧');
  }

  // ══════════════════════════════════════════════════════════════
  // 辅助函数
  // ══════════════════════════════════════════════════════════════

  /** HTML 转义（优先使用 ChemAPI，不可用时自实现） */
  function _esc(str) {
    if (typeof ChemAPI !== 'undefined' && ChemAPI.escapeHtml) {
      return ChemAPI.escapeHtml(String(str));
    }
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  /** 保留 LaTeX 公式的转义：$...$ 和 $$...$$ 不转义 */
  function _escapeLatex(text) {
    if (!text) return '';
    var str = String(text);
    // 先提取所有 LaTeX 块
    var latexBlocks = [];
    str = str.replace(/\$\$([^$]+)\$\$/g, function (_, formula) {
      latexBlocks.push('$$' + formula + '$$');
      return '\x00LATEX\x00';
    });
    str = str.replace(/\$([^$]+)\$/g, function (_, formula) {
      latexBlocks.push('$' + formula + '$');
      return '\x00LATEX\x00';
    });
    // 转义剩余 HTML
    str = _esc(str);
    // 还原 LaTeX
    var idx = 0;
    str = str.replace(/\x00LATEX\x00/g, function () {
      return latexBlocks[idx++] || '';
    });
    // 换行转 <br>
    str = str.replace(/\n/g, '<br>');
    return str;
  }

  /** 从 tool_result 提取文本内容 */
  function _extractText(result) {
    if (!result) return '';
    if (typeof result === 'string') return result;
    if (result.result && typeof result.result === 'string') return result.result;
    if (result.text) return result.text;
    if (result.content) return result.content;
    if (result.message) return result.message;
    // 尝试 JSON 序列化兜底
    try { return JSON.stringify(result, null, 2); } catch (e) { return String(result); }
  }

  /** 渲染步骤卡片 */
  function _renderSteps(steps, result) {
    var text = _extractText(result);
    var html = '';
    for (var i = 0; i < steps.length; i++) {
      var s = steps[i];
      html += (
        '<div class="step-row">'
        + '<div class="step-num">' + s.icon + ' ' + s.num + '</div>'
        + '<div class="step-content">'
        + '<div class="step-title">' + _esc(s.title) + '</div>'
        + '<div class="step-desc">' + _esc(s.desc) + '</div>'
        + '</div>'
        + '</div>'
      );
    }
    // 追加工具输出的实际辅导文本
    if (text) {
      html += '<div class="tutor-text" style="margin-top:12px">' + _escapeLatex(text) + '</div>';
    }
    return html;
  }

  // ══════════════════════════════════════════════════════════════
  // 公共入口
  // ══════════════════════════════════════════════════════════════

  /** 渲染器注册表 */
  var _renderers = {
    chemistry_tutor: _renderChemistryTutor,
    ionic_equation_tutor: _renderIonicEquationTutor,
    stoichiometry_tutor: _renderStoichiometryTutor,
    redox_tutor: _renderRedoxTutor,
    equilibrium_tutor: _renderEquilibriumTutor,
    periodic_law_tutor: _renderPeriodicLawTutor,
    organic_tutor: _renderChemistryTutor,      // 复用通用辅导
    simulate_experiment: _renderSimulateExperiment,
    web_search: _renderChemistryTutor,          // 搜索结果文本展示
  };

  /**
   * 统一渲染入口
   * @param {string} toolName — 工具名
   * @param {object|string} result — tool_result 的 data
   * @returns {string} HTML 字符串
   */
  function render(toolName, result) {
    if (!toolName) {
      return _renderFallback('unknown', result);
    }
    var renderer = _renderers[toolName];
    if (typeof renderer === 'function') {
      try {
        return renderer(result);
      } catch (e) {
        console.error('[ChemAgentRender] 渲染 ' + toolName + ' 失败:', e);
        return _renderFallback(toolName, result);
      }
    }
    return _renderFallback(toolName, result);
  }

  // ══════════════════════════════════════════════════════════════

  return {
    render: render,
    toolLabel: toolLabel,
  };
})();
