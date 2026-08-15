"""ChemAI — Agent 工具模块。

导入所有工具模块以触发 @register_tool 装饰器注册。
导入顺序无关紧要——装饰器在 import 时即执行，仅存储元数据，
不触发任何重量级初始化（如浏览器启动）。
"""

# ── 工具元数据注册中心（必须最先导入） ──
from agent.tools import tool_meta  # noqa: F401

# ── 领域工具 ──
from agent.tools import exam_tools  # noqa: F401
from agent.tools import diagnosis_tools  # noqa: F401
from agent.tools import tutoring_tools  # noqa: F401
from agent.tools import socratic_tutors  # noqa: F401
from agent.tools import organic_tutor  # noqa: F401
from agent.tools import periodic_law_tutor  # noqa: F401
from agent.tools import memory_tools  # noqa: F401
from agent.tools import parent_tools  # noqa: F401
from agent.tools import ocr_progress  # noqa: F401
from agent.tools import grading_trigger  # noqa: F401
from agent.tools import grading_save  # noqa: F401

# ── 浏览器工具（Playwright 可选依赖） ──
try:
    from agent.tools import browser_tools  # noqa: F401
except ImportError:
    pass  # Playwright 未安装时跳过浏览器工具
