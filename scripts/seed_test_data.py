"""种子数据脚本 — 幂等地补齐演示所需的学校/教师/学生/题目/试卷/预警/练习/错题/复习。

设计（验收修复 ISSUE-002/003）：
- 不再因「存在任意 Account」就整体跳过，改为逐实体「find-or-create」。
- 复用已存在的学校/年级/班级/账号，缺失的才创建。
- 补齐教师档案 + 任课关系 + 试卷 + 预警 + 家长绑定。
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.config import DATABASE_URL
from app.models import Base
from app.models.user import (
    Account, Student, Teacher, TeacherClassSubject, Parent,
)
from app.models.org import School, Grade, Class as ClassModel
from app.models.teaching import Question, PracticeSession, PracticeSessionQuestion, StudentAnswer, ExamRecord
from app.models.diagnosis import ReviewTask, WarningLog, KnowledgePoint
from app.models.exam_paper import ExamPaper, ExamPaperQuestion
from app.models.homework import StudentParentBinding
from app.core.enums import (
    AccountRole, StudentStatus, TeacherRole, TeacherAccountStatus,
    QuestionType, Difficulty, QuestionSource,
    PracticeSessionStatus, ReviewTaskStatus,
    ExamPaperStatus, WarningType, WarningSeverity, WarningStatus,
    BindingStatus, ParentRelation, ExamType, ExamRecordStatus,
)
from app.core.security import create_access_token, hash_password
from app.seed import CHEMISTRY_KNOWLEDGE_POINTS

# 演示账号统一口令。旧弱口令 test123 的 bcrypt 哈希已随 data/chemai.db.bak 泄露进公开仓库，
# 此处换强口令并在 seed 时轮换，使泄露哈希作废（幂等）。
DEMO_PASSWORD = "Demo@2026"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _get_or_create(db, model, where_clause, factory):
    """按条件查实体，不存在则用 factory() 创建并 flush，返回 (实体, 是否新建)。"""
    obj = (await db.execute(select(model).where(where_clause))).scalar_one_or_none()
    if obj is not None:
        return obj, False
    obj = factory()
    db.add(obj)
    await db.flush()
    return obj, True


async def seed():
    async with AsyncSessionLocal() as db:
        # ── 1. School / Grade / Class（幂等复用）──
        school, _ = await _get_or_create(
            db, School, School.name == "测试中学",
            lambda: School(name="测试中学", region="测试区"),
        )
        grade, _ = await _get_or_create(
            db, Grade, Grade.school_id == school.id,
            lambda: Grade(name="高一", school_id=school.id),
        )
        class_, _ = await _get_or_create(
            db, ClassModel, ClassModel.grade_id == grade.id,
            lambda: ClassModel(name="高一(1)班", grade_id=grade.id),
        )

        # ── 1.5 Knowledge Points（出题工作台知识点选择器依赖此表，find-or-create）──
        for kp in CHEMISTRY_KNOWLEDGE_POINTS:
            exists = (await db.execute(
                select(KnowledgePoint).where(KnowledgePoint.name == kp["name"])
            )).scalar_one_or_none()
            if exists is None:
                db.add(KnowledgePoint(**kp))

        # ── 2. Teacher Account + Profile + 任课关系 ──
        t_acc, _ = await _get_or_create(
            db, Account, Account.phone == "13800000001",
            lambda: Account(phone="13800000001", password_hash=hash_password(DEMO_PASSWORD), role=AccountRole.teacher),
        )
        t_acc.password_hash = hash_password(DEMO_PASSWORD)  # 轮换：使历史泄露哈希作废
        teacher, _ = await _get_or_create(
            db, Teacher, Teacher.account_id == t_acc.id,
            lambda: Teacher(
                account_id=t_acc.id, school_id=school.id, name="张老师",
                status=TeacherAccountStatus.approved, role=TeacherRole.teacher,
            ),
        )
        await _get_or_create(
            db, TeacherClassSubject,
            (TeacherClassSubject.teacher_id == teacher.id) & (TeacherClassSubject.class_id == class_.id),
            lambda: TeacherClassSubject(teacher_id=teacher.id, class_id=class_.id, subject="化学", is_head_teacher=True),
        )

        # ── 3. Student Account + Profile ──
        s_acc, _ = await _get_or_create(
            db, Account, Account.phone == "13800000002",
            lambda: Account(phone="13800000002", password_hash=hash_password(DEMO_PASSWORD), role=AccountRole.student),
        )
        s_acc.password_hash = hash_password(DEMO_PASSWORD)  # 轮换：使历史泄露哈希作废
        student, _ = await _get_or_create(
            db, Student, Student.account_id == s_acc.id,
            lambda: Student(
                account_id=s_acc.id, class_id=class_.id, school_id=school.id,
                name="测试学生", student_id=f"S{uuid.uuid4().hex[:6].upper()}",
                status=StudentStatus.approved.value, is_activated=True,
                barrier_profile={"concept": 0.5, "reading": 0.3, "expression": 0.2},
                weak_knowledge_points=["氧化还原反应", "离子反应"],
            ),
        )
        student_id = student.id

        # ── 4. Questions（仅当题目表为空）──
        question_count = (await db.execute(select(func.count(Question.id)))).scalar_one()
        question_ids = []
        if question_count == 0:
            questions_config = [
                # (content, question_type, options, answer, difficulty, kps)
                ("下列物质中，属于电解质的是？", "choice",
                 ["A. 蔗糖", "B. NaCl溶液", "C. 熔融NaOH", "D. 酒精"], "C", "medium", ["电解质"]),
                ("$2Fe + 3Cl_2 \\rightarrow 2FeCl_3$ 的反应类型是？", "choice",
                 ["A. 置换反应", "B. 化合反应", "C. 分解反应", "D. 复分解反应"], "B", "easy", ["氧化还原反应"]),
                ("$\\ce{Na2CO3 + 2HCl -> 2NaCl + H2O + CO2}$ 中，被氧化的元素是？", "choice",
                 ["A. Na", "B. C", "C. O", "D. 无"], "D", "medium", ["离子反应"]),
                ("$pH=3$ 的盐酸溶液中，$[H^+]$ 是多少？", "choice",
                 ["A. $10^{-3}$ mol/L", "B. $10^{-11}$ mol/L", "C. $3$ mol/L", "D. $0.003$ mol/L"], "A", "easy", ["溶液酸碱性"]),
                ("下列操作中，不能用于检验$Fe^{3+}$的是？", "choice",
                 ["A. KSCN溶液", "B. NaOH溶液", "C. $K_4[Fe(CN)_6]$溶液", "D. AgNO₃溶液"], "D", "hard", ["离子检验"]),
                ("$1mol$ $H_2SO_4$ 中含有氧原子的数目为？", "choice",
                 ["A. $6.02\\times10^{23}$", "B. $1.204\\times10^{24}$", "C. $2.408\\times10^{24}$", "D. $4.816\\times10^{24}$"], "C", "medium", ["物质的量"]),
                ("化学键的类型包括哪些？", "fill_blank",
                 None, "离子键、共价键、金属键", "easy", ["化学键"]),
                ("写出铝与氢氧化钠溶液反应的化学方程式。", "fill_blank",
                 None, "$2Al + 2NaOH + 2H_2O = 2NaAlO_2 + 3H_2\\uparrow$", "medium", ["化学方程式"]),
                ("在标准状况下，$22.4L$ $CO_2$ 的质量为？", "choice",
                 ["A. 22g", "B. 44g", "C. 88g", "D. 11g"], "B", "easy", ["气体摩尔体积"]),
                ("下列关于催化剂的说法正确的是？", "choice",
                 ["A. 催化剂不参与反应", "B. 催化剂能改变反应热", "C. 催化剂能降低活化能", "D. 催化剂只加快正反应速率"], "C", "medium", ["化学反应速率"]),
            ]
            for content, qt_str, opts, ans, diff, kps in questions_config:
                q = Question(
                    content=content,
                    question_type=QuestionType(qt_str),
                    options=opts,
                    answer=ans,
                    difficulty=Difficulty(diff),
                    knowledge_point_tags=kps,
                    source=QuestionSource.ai_generated,
                )
                db.add(q)
                await db.flush()
                question_ids.append(q.id)
        else:
            question_ids = list((await db.execute(select(Question.id))).scalars().all())

        # ── 5. Exam Paper（仅当无试卷时创建，含 5 道题）──
        paper_count = (await db.execute(select(func.count(ExamPaper.id)))).scalar_one()
        if paper_count == 0 and question_ids:
            paper = ExamPaper(
                name="高一化学单元测试（氧化还原与离子反应）",
                total_score=100, duration_minutes=60,
                status=ExamPaperStatus.published, teacher_id=teacher.id,
            )
            db.add(paper)
            await db.flush()
            for i, qid in enumerate(question_ids[:5]):
                db.add(ExamPaperQuestion(exam_paper_id=paper.id, question_id=qid, sort_order=i, score=20.0))
            await db.flush()

        # ── 5.5 ExamRecord（仅当无考试记录时创建，把试卷衔接进班级，供「发布考试→学情」演示）──
        exam_record_count = (await db.execute(select(func.count(ExamRecord.id)))).scalar_one()
        if exam_record_count == 0:
            paper_ref = (await db.execute(
                select(ExamPaper).where(ExamPaper.status == ExamPaperStatus.published).limit(1)
            )).scalar_one_or_none()
            db.add(ExamRecord(
                class_id=class_.id,
                exam_paper_id=paper_ref.id if paper_ref else None,
                exam_type=ExamType.monthly,
                status=ExamRecordStatus.completed,
                exam_date=datetime.now(timezone.utc) - timedelta(days=3),
                name="高一化学月考（第一单元）",
                participant_count=1,
                avg_score=82.0,
                error_stats={"class_avg": 82.0},
            ))
            await db.flush()

        # ── 6. Practice Sessions + StudentAnswer（仅当无练习会话时创建）──
        ps_count = (await db.execute(select(func.count(PracticeSession.id)))).scalar_one()
        if ps_count == 0 and question_ids:
            ps = PracticeSession(
                student_id=student_id,
                practice_id=f"PR-{uuid.uuid4().hex[:8].upper()}",
                title="氧化还原与离子反应练习",
                barrier_type="concept",
                question_count=5,
                status=PracticeSessionStatus.completed,
                created_at=datetime.now(timezone.utc) - timedelta(hours=2),
            )
            db.add(ps)
            await db.flush()
            for i, qid in enumerate(question_ids[:5]):
                db.add(PracticeSessionQuestion(practice_session_id=ps.id, question_id=qid, sort_order=i))
                is_correct = i >= 3
                db.add(StudentAnswer(
                    student_id=student_id, question_id=qid,
                    answer_content="" if is_correct else "错误答案",
                    is_correct=is_correct,
                ))
            await db.flush()

            ps2 = PracticeSession(
                student_id=student_id,
                practice_id=f"PR-{uuid.uuid4().hex[:8].upper()}",
                title="物质的量与化学键练习",
                barrier_type="expression",
                question_count=3,
                status=PracticeSessionStatus.in_progress,
                created_at=datetime.now(timezone.utc) - timedelta(minutes=30),
            )
            db.add(ps2)
            await db.flush()
            for i, qid in enumerate(question_ids[5:8]):
                db.add(PracticeSessionQuestion(practice_session_id=ps2.id, question_id=qid, sort_order=i))
            await db.flush()

        # ── 7. ReviewTask（仅当无复习任务时创建）──
        rt_count = (await db.execute(select(func.count(ReviewTask.id)))).scalar_one()
        if rt_count == 0 and question_ids:
            now = datetime.now(timezone.utc)
            for i, qid in enumerate(question_ids[:3]):
                db.add(ReviewTask(
                    student_id=student_id, question_id=qid, level=i,
                    status=ReviewTaskStatus.pending,
                    consecutive_correct=0, consecutive_wrong=1,
                    next_review_date=now - timedelta(days=i),
                ))
            await db.flush()

        # ── 8. WarningLog（仅当无预警时创建）──
        wl_count = (await db.execute(select(func.count(WarningLog.id)))).scalar_one()
        if wl_count == 0:
            db.add(WarningLog(
                student_id=student_id, warning_type=WarningType.high_error_rate,
                severity=WarningSeverity.warning, title="氧化还原练习错误率偏高",
                message="最近一次练习错误率超过 50%，建议针对性辅导氧化还原反应。",
                status=WarningStatus.pending,
                notified_teacher=False, notified_parent=False, notified_student=False,
            ))
            db.add(WarningLog(
                student_id=student_id, warning_type=WarningType.new_barrier,
                severity=WarningSeverity.severe, title="新障碍：离子反应概念混淆",
                message="学生在离子反应相关题目中连续出错，可能存在概念性障碍。",
                status=WarningStatus.pending,
                notified_teacher=False, notified_parent=False, notified_student=False,
            ))
            await db.flush()

        # ── 9. Parent Accounts + Profiles + Bindings（find-or-create，口令无条件轮换）──
        # 修复 D-01：家长口令轮换需像教师/学生一样放在条件块之外，
        # 否则绑定已存在时（如经 /auth/register/parent 注册过）口令不会轮换到 DEMO_PASSWORD。
        # 文档（e2e-test-steps.md §0.3）演示 3 个家长账号，均绑定到该学生。
        for parent_phone in ("13900000100", "13900000101", "13900000999"):
            p_acc, _ = await _get_or_create(
                db, Account, Account.phone == parent_phone,
                lambda: Account(phone=parent_phone, password_hash=hash_password(DEMO_PASSWORD), role=AccountRole.parent),
            )
            p_acc.password_hash = hash_password(DEMO_PASSWORD)  # 轮换：使注册流旧口令作废
            parent, _ = await _get_or_create(
                db, Parent, Parent.account_id == p_acc.id,
                lambda: Parent(account_id=p_acc.id, name="测试家长"),
            )
            # 幂等绑定：仅当该 (student, parent) 尚无绑定时创建
            binding_exists = (await db.execute(
                select(StudentParentBinding).where(
                    StudentParentBinding.student_id == student_id,
                    StudentParentBinding.parent_id == parent.id,
                )
            )).scalar_one_or_none()
            if binding_exists is None:
                db.add(StudentParentBinding(
                    student_id=student_id, parent_id=parent.id,
                    status=BindingStatus.active, relation=ParentRelation.father,
                ))
                await db.flush()

        await db.commit()

        # ── 打印结果 ──
        token = create_access_token(user_id=s_acc.id, role="student", school_id=school.id)
        print(f"=== Seed Complete ===")
        print(f"School ID:     {school.id}")
        print(f"Teacher ID:    {teacher.id} (account {t_acc.id})")
        print(f"Student ID:    {student_id} (account {s_acc.id})")
        print(f"Question IDs:  {question_ids}")
        print(f"JWT Token (student, school_id={school.id}):")
        print(f"  Bearer {token}")


if __name__ == "__main__":
    asyncio.run(seed())
