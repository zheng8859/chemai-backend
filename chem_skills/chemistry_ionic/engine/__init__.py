"""离子反应辅导引擎 — 四步法（可解离→离子形式→去旁观→验证守恒）。

导出：
- classify_electrolyte: 判断电解质类型（强/弱/非）
- write_ionic_form: 将分子方程式改写为离子形式
- remove_spectators: 识别并删除旁观离子
- verify_net_ionic: 验证净离子方程式的守恒
"""

from .models import IonicAnalysis, ElectrolyteType
from .tutor import (
    classify_electrolyte,
    write_ionic_form,
    remove_spectators,
    verify_net_ionic,
)

__all__ = [
    "IonicAnalysis",
    "ElectrolyteType",
    "classify_electrolyte",
    "write_ionic_form",
    "remove_spectators",
    "verify_net_ionic",
]
