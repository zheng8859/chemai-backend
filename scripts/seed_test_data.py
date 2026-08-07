"""种子数据脚本 — 创建核心流程测试所需的学校/学生/题目/练习/错题/复习。"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.config import DATABASE_URL
from app.models import Base
from app.models.user import Account, Student, Teacher
from app.models.org import School, Grade, Class as ClassModel
from app.models.teaching import Question, PracticeSession, PracticeSessionQuestion, StudentAnswer
from app.models.diagnosis import ReviewTask, ReviewHistory
from app.core.enums import (
    AccountRole, StudentStatus, QuestionType, Difficulty, QuestionSource,
    PracticeSessionStatus, ReviewTaskStatus,
)
from app.core.security import create_access_token, hash_password

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def seed():
    async with AsyncSessionLocal() as db:
        # ── 检查是否已有数据 ──
        r = await db.execute(select(Account).limit(1))
        if r.scalar_one_or_none():
            print("数据已存在，跳过 seed")
            return

        # ── School ──
        school = School(name="测试中学", region="测试区")
        db.add(school)
        await db.flush()

        # ── Grade + Class ──
        grade = Grade(name="高一", school_id=school.id)
        db.add(grade)
        await db.flush()
        class_ = ClassModel(name="高一(1)班", grade_id=grade.id)
        db.add(class_)
        await db.flush()

        # ── Teacher Account + Teacher ──
        t_acc = Account(phone="13800000001", password_hash=hash_password("test123"), role=AccountRole.teacher)
        db.add(t_acc)
        await db.flush()
        teacher = Teacher(
            account_id=t_acc.id, school_id=school.id, name="张老师",
        )
        db.add(teacher)
        await db.flush()

        # ── Student Account + Student ──
        s_acc = Account(phone="13800000002", password_hash=hash_password("test123"), role=AccountRole.student)
        db.add(s_acc)
        await db.flush()
        sid = s_acc.id  # account id = user id
        student = Student(
            account_id=s_acc.id, class_id=class_.id, school_id=school.id,
            name="测试学生", student_id=f"S{uuid.uuid4().hex[:6].upper()}",
            status=StudentStatus.approved.value,
            is_activated=True,
            barrier_profile={"concept": 0.5, "reading": 0.3, "expression": 0.2},
            weak_knowledge_points=["氧化还原反应", "离子反应"],
        )
        db.add(student)
        await db.flush()
        student_id = student.id

        # ── 10 道化学题目 ──
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
        question_ids = []
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

        # ── 练习会话（已完成） ──
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
            psq = PracticeSessionQuestion(
                practice_session_id=ps.id,
                question_id=qid,
                sort_order=i,
            )
            db.add(psq)
            # 前 3 题答错（制造错题），后 2 题答对
            is_correct = i >= 3
            sa = StudentAnswer(
                student_id=student_id,
                question_id=qid,
                answer_content="" if is_correct else "错误答案",
                is_correct=is_correct,
            )
            db.add(sa)
        await db.flush()

        # ── 练习会话（进行中） ──
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
            psq = PracticeSessionQuestion(
                practice_session_id=ps2.id,
                question_id=qid,
                sort_order=i,
            )
            db.add(psq)
        await db.flush()

        # ── ReviewTask（3 个错题 → 复习任务） ──
        now = datetime.now(timezone.utc)
        for i, qid in enumerate(question_ids[:3]):
            rt = ReviewTask(
                student_id=student_id,
                question_id=qid,
                level=i,  # 0, 1, 2
                status=ReviewTaskStatus.pending,
                consecutive_correct=0,
                consecutive_wrong=1,
                next_review_date=now - timedelta(days=i),  # Level 0 已逾期
            )
            db.add(rt)
        await db.flush()

        await db.commit()

        # ── 打印结果 ──
        token = create_access_token(user_id=sid, role="student", school_id=school.id)
        print(f"=== Seed Complete ===")
        print(f"School ID:     {school.id}")
        print(f"Student ID:    {student_id}")
        print(f"Account ID (uid): {sid}")
        print(f"Question IDs:  {question_ids}")
        print(f"Completed Session: PR-...")
        print(f"In-progress Session: PR-...")
        print(f"ReviewTasks:   3 (Levels 0, 1, 2)")
        print(f"")
        print(f"JWT Token (student, school_id={school.id}):")
        print(f"  Bearer {token}")
        print(f"")
        print(f"Test flow:")
        print(f"  1. GET  /api/v1/practice/student/{sid}/tasks")
        print(f"  2. POST /api/v1/practice/submit")
        print(f"  3. GET  /api/v1/practice/wrong/list?student_id={sid}")
        print(f"  4. GET  /api/v1/review/student/{sid}/due")
        print(f"  5. POST /api/v1/review/submit")
        print(f"  6. POST /api/v1/practice/wrong-topic/variant/generate")
        print(f"  7. POST /api/v1/practice/wrong-topic/training/create")
        print(f"  8. POST /api/v1/practice/wrong-topic/training/submit")


if __name__ == "__main__":
    asyncio.run(seed())
