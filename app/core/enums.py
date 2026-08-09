"""ChemAI 枚举类型 — 对齐领域模型，含 45-数据模型与认证体系 新增枚举。"""

from enum import Enum


# ── 账户角色 (34号 §二, 23号 §一) ───────────────────────────
class AccountRole(str, Enum):
    teacher = "teacher"
    student = "student"
    parent = "parent"


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


# ── 学生账号状态 (23号 §六) ─────────────────────────────────
class StudentStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


# ── 亲子关系 (34号 §四) ────────────────────────────────────
class ParentRelation(str, Enum):
    father = "father"
    mother = "mother"
    other = "other"


# ── 绑定状态 (34号 §四) ────────────────────────────────────
class BindingStatus(str, Enum):
    active = "active"
    inactive = "inactive"


# ── 预警类型 (34号 §三.4) ──────────────────────────────────
class WarningType(str, Enum):
    consecutive_absence = "consecutive_absence"  # 连续未登录
    score_drop = "score_drop"                    # 成绩下滑
    high_error_rate = "high_error_rate"          # 高错误率
    new_barrier = "new_barrier"                  # 新障碍出现


# ── 预警状态 (34号 §三.4) ──────────────────────────────────
class WarningStatus(str, Enum):
    pending = "pending"        # 新生成，等待教师查看
    processing = "processing"  # 教师已查看，正在处理中
    resolved = "resolved"      # 已处理完成
    dismissed = "dismissed"    # 教师判定为误报，手动忽略


# ── 预警严重级别 (34号 §三.4) ──────────────────────────────
class WarningSeverity(str, Enum):
    info = "info"        # 提示
    warning = "warning"  # 警告
    severe = "severe"    # 严重


# ── 通知类型 (34号 §四) ────────────────────────────────────
class NotificationType(str, Enum):
    learning_report = "learning_report"  # 学习报告
    warning_alert = "warning_alert"      # 预警提醒
    teacher_message = "teacher_message"  # 教师消息


# ── 教师入驻申请状态 (23号 §五) ────────────────────────────
class ApplicationStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


# ── OCR 批改任务状态 (34号 §五.3) ──────────────────────────
class OCRTaskStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    done = "done"
    failed = "failed"


# ── Agent 记忆类型 (34号 §七.2) ────────────────────────────
class MemoryType(str, Enum):
    student_diagnosis_history = "student_diagnosis_history"
    teacher_preference = "teacher_preference"


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


# ── 迷思概念类别 (45-数据模型与认证体系 §三) ─────────────────
class MisconceptionCategory(str, Enum):
    chemical_equilibrium = "chemical_equilibrium"    # 化学平衡
    redox = "redox"                                  # 氧化还原
    mole_calculation = "mole_calculation"            # 摩尔计算
    organic_chemistry = "organic_chemistry"          # 有机化学
    chemical_notation = "chemical_notation"          # 化学用语
    structure_of_matter = "structure_of_matter"      # 物构知识


# ── 题目类型 (45-数据模型与认证体系 §三) ─────────────────────
class QuestionType(str, Enum):
    choice = "choice"                          # 选择题
    fill_blank = "fill_blank"                  # 填空题
    calculation = "calculation"                # 计算题
    equation_balancing = "equation_balancing"  # 方程式配平
    experiment_inquiry = "experiment_inquiry"  # 实验探究


# ── 试卷状态 (45-数据模型与认证体系 §四) ─────────────────────
class ExamPaperStatus(str, Enum):
    draft = "draft"          # 草稿
    published = "published"  # 已发布
    archived = "archived"    # 已归档


# ── 考试记录状态 (45-数据模型与认证体系 §四) ─────────────────
class ExamRecordStatus(str, Enum):
    pending = "pending"          # 待开始
    in_progress = "in_progress"  # 进行中
    grading = "grading"          # 批改中
    completed = "completed"      # 已完成
    archived = "archived"        # 已归档
    cancelled = "cancelled"      # 已取消


# ── 自适应练习会话状态 (45-数据模型与认证体系 §五) ───────────
class PracticeSessionStatus(str, Enum):
    in_progress = "in_progress"  # 进行中
    completed = "completed"      # 已完成
    abandoned = "abandoned"      # 已放弃


# ── 审批状态 (45-数据模型与认证体系 §六) ─────────────────────
class ApprovalStatus(str, Enum):
    pending = "pending"      # 待审批
    approved = "approved"    # 已通过
    rejected = "rejected"    # 已拒绝
    expired = "expired"      # 已过期


# ── 诊断来源 (45-数据模型与认证体系 §三) ─────────────────────
class DiagnosisSource(str, Enum):
    ai_rule = "ai_rule"      # 规则引擎
    ai_llm = "ai_llm"        # LLM 深度诊断
    teacher = "teacher"      # 教师手动覆盖
