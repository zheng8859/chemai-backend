"""ChemAI 枚举类型 — 从 34-数据模型设计 §八 提取。"""

from enum import Enum


# ── 障碍类型 (34号 §八, 27号 §二) ──────────────────────────
class BarrierType(str, Enum):
    concept = "concept"        # 概念理解型
    reading = "reading"        # 审题障碍型
    expression = "expression"  # 表述障碍型


# ── 考试类型 (34号 §八) ────────────────────────────────────
class ExamType(str, Enum):
    monthly = "monthly"  # 月考
    practice = "practice"  # 练习
    homework = "homework"  # 作业


# ── 题目来源 (34号 §八) ────────────────────────────────────
class QuestionSource(str, Enum):
    ai_generated = "ai_generated"  # AI 生成
    manual = "manual"              # 手动录入
    daily_practice = "daily_practice"  # 每日练习
    ocr_import = "ocr_import"      # OCR 导入


# ── 题目审核状态 (34号 §八) ────────────────────────────────
class AuditStatus(str, Enum):
    passed = "passed"      # 通过
    warning = "warning"    # 警告可用
    blocked = "blocked"    # 阻断不可用


# ── 题目难度 (34号 §八) ────────────────────────────────────
class Difficulty(str, Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"
    competition = "competition"  # 竞赛级，不自动分配


# ── 教师角色 (34号 §二) ────────────────────────────────────
class TeacherRole(str, Enum):
    system_admin = "system_admin"    # 系统管理员
    academic_admin = "academic_admin"  # 教务管理员
    subject_lead = "subject_lead"    # 学科组长
    teacher = "teacher"              # 普通教师


# ── 教师账号状态 (34号 §二) ─────────────────────────────────
class TeacherAccountStatus(str, Enum):
    pending = "pending"    # 待审核
    approved = "approved"  # 已通过
    rejected = "rejected"  # 已拒绝


# ── 复习任务状态 (34号 §三) ────────────────────────────────
class ReviewTaskStatus(str, Enum):
    pending = "pending"      # 待复习
    overdue = "overdue"      # 已过期
    completed = "completed"  # 已完成


# ── OCR 会话状态 (34号 §五) ────────────────────────────────
class UploadSessionStatus(str, Enum):
    uploaded = "uploaded"
    previewing = "previewing"
    ready = "ready"
    importing = "importing"
    imported = "imported"
    grading = "grading"
    graded = "graded"
    done = "done"
    discarded = "discarded"
    error = "error"
