"""Seed data for ChemAI development — idempotent, safe to run multiple times.

Populates:
- Knowledge Points (chemistry domain)
- Demo School → Grade → Class chain
- Default BarrierConfig per teacher
- Sample Historical Exam questions

Usage:
    cd chemai-backend
    source venv/Scripts/activate
    python -m app.seed
"""

import asyncio
from datetime import datetime

from sqlalchemy import select, func

from .infrastructure.database import MainSession
from .models import School, Grade, Class
from .models.user import Teacher, Account, TeacherClassSubject
from .models.diagnosis import BarrierConfig, KnowledgePoint
from .models.question_bank import HistoricalExam
from .core.enums import (
    AccountRole,
    TeacherRole,
    TeacherAccountStatus,
    Difficulty,
)
from .core.security import hash_password


# ═══════════════════════════════════════════════════════════
# Knowledge Points (chemistry domain)
# ═══════════════════════════════════════════════════════════

CHEMISTRY_KNOWLEDGE_POINTS: list[dict] = [
    # 无机化学
    {"name": "氧化还原反应", "category": "无机化学"},
    {"name": "离子反应", "category": "无机化学"},
    {"name": "化学计量", "category": "无机化学"},
    {"name": "元素周期律", "category": "无机化学"},
    {"name": "化学键", "category": "无机化学"},
    {"name": "分子结构与性质", "category": "无机化学"},
    {"name": "晶体结构", "category": "无机化学"},
    # 电化学
    {"name": "原电池", "category": "电化学"},
    {"name": "电解池", "category": "电化学"},
    {"name": "金属腐蚀与防护", "category": "电化学"},
    # 电解质溶液
    {"name": "电解质溶液", "category": "电解质溶液"},
    {"name": "盐类水解", "category": "电解质溶液"},
    {"name": "酸碱中和滴定", "category": "电解质溶液"},
    {"name": "沉淀溶解平衡", "category": "电解质溶液"},
    # 化学平衡
    {"name": "化学平衡", "category": "化学平衡"},
    {"name": "化学平衡常数", "category": "化学平衡"},
    {"name": "化学反应速率", "category": "化学平衡"},
    {"name": "勒夏特列原理", "category": "化学平衡"},
    # 热化学
    {"name": "热化学方程式", "category": "热化学"},
    {"name": "盖斯定律", "category": "热化学"},
    {"name": "反应热计算", "category": "热化学"},
    # 有机化学
    {"name": "有机化合物命名", "category": "有机化学"},
    {"name": "同分异构体", "category": "有机化学"},
    {"name": "烃的性质", "category": "有机化学"},
    {"name": "卤代烃", "category": "有机化学"},
    {"name": "醇与酚", "category": "有机化学"},
    {"name": "醛与酮", "category": "有机化学"},
    {"name": "羧酸与酯", "category": "有机化学"},
    {"name": "有机合成路线", "category": "有机化学"},
    # 物质结构
    {"name": "原子结构", "category": "物质结构"},
    {"name": "核外电子排布", "category": "物质结构"},
    {"name": "杂化轨道理论", "category": "物质结构"},
    {"name": "价层电子对互斥理论", "category": "物质结构"},
    # 实验化学
    {"name": "常见仪器与操作", "category": "实验化学"},
    {"name": "物质的分离与提纯", "category": "实验化学"},
    {"name": "物质的检验与鉴别", "category": "实验化学"},
    {"name": "气体制备与收集", "category": "实验化学"},
    {"name": "定量实验", "category": "实验化学"},
]

DEMO_HISTORICAL_EXAMS: list[dict] = [
    {
        "source": "全国卷",
        "year": 2024,
        "question_number": "7",
        "knowledge_point_tags": ["氧化还原反应"],
        "difficulty": Difficulty.medium,
        "discrimination": 0.45,
        "content": "下列反应中，属于氧化还原反应的是（  ）\nA. CaCO₃ → CaO + CO₂↑\nB. 2Na + Cl₂ → 2NaCl\nC. NaOH + HCl → NaCl + H₂O\nD. AgNO₃ + NaCl → AgCl↓ + NaNO₃",
        "answer": "B",
        "analysis": "氧化还原反应的特征是元素化合价变化。B中Na由0→+1，Cl由0→-1。A/C/D均无化合价变化。",
    },
    {
        "source": "全国卷",
        "year": 2024,
        "question_number": "12",
        "knowledge_point_tags": ["化学平衡", "勒夏特列原理"],
        "difficulty": Difficulty.hard,
        "discrimination": 0.62,
        "content": "在2NO₂(g) ⇌ N₂O₄(g) ΔH<0反应中，下列操作能使平衡向正反应方向移动的是（  ）\nA. 升高温度\nB. 增大压强\nC. 加入催化剂\nD. 减小N₂O₄浓度",
        "answer": "B",
        "analysis": "正反应气体分子数减少（2→1），增大压强平衡向气体分子数减少方向移动。ΔH<0说明正反应放热，升温向逆方向移动。催化剂不影响平衡。",
    },
    {
        "source": "湖南卷",
        "year": 2024,
        "question_number": "8",
        "knowledge_point_tags": ["盐类水解", "电解质溶液"],
        "difficulty": Difficulty.medium,
        "discrimination": 0.38,
        "content": "下列关于盐类水解的说法正确的是（  ）\nA. 强酸强碱盐一定不水解\nB. 升高温度抑制盐类水解\nC. 稀释促进盐类水解\nD. 加入酸一定促进盐类水解",
        "answer": "C",
        "analysis": "稀释时离子浓度降低，根据平衡移动原理，水解平衡向离子数增多的方向即水解方向移动。A错误（如AlCl₃水解），B错误（水解吸热升温促进），D过于绝对。",
    },
    {
        "source": "湖南卷",
        "year": 2023,
        "question_number": "10",
        "knowledge_point_tags": ["原电池", "电化学"],
        "difficulty": Difficulty.easy,
        "discrimination": 0.30,
        "content": "铜锌原电池（丹尼尔电池）中，负极发生的反应是（  ）\nA. Cu²⁺ + 2e⁻ → Cu\nB. Zn → Zn²⁺ + 2e⁻\nC. 2H⁺ + 2e⁻ → H₂↑\nD. O₂ + 4H⁺ + 4e⁻ → 2H₂O",
        "answer": "B",
        "analysis": "铜锌原电池中锌比铜活泼，锌为负极发生氧化反应：Zn → Zn²⁺ + 2e⁻。A是正极反应，C/D不是该电池反应。",
    },
]


async def seed_knowledge_points(session) -> int:
    """Seed chemistry knowledge points. Returns count created."""
    count = 0
    for kp in CHEMISTRY_KNOWLEDGE_POINTS:
        exists = await session.execute(
            select(KnowledgePoint).where(KnowledgePoint.name == kp["name"])
        )
        if exists.scalar_one_or_none() is None:
            session.add(KnowledgePoint(**kp))
            count += 1
    if count:
        await session.commit()
    return count


async def seed_demo_org(session) -> tuple[School, Grade, Class, Teacher]:
    """Create demo school → grade → class → teacher chain if not exists.

    Returns the demo entities (existing or newly created).
    """
    # School
    result = await session.execute(
        select(School).where(School.name == "ChemAI 演示学校")
    )
    school = result.scalar_one_or_none()
    if school is None:
        school = School(
            name="ChemAI 演示学校",
            region="湖南省",
            address="长沙市岳麓区",
            current_semester="2026春",
        )
        session.add(school)
        await session.flush()

    # Grade
    result = await session.execute(
        select(Grade).where(
            Grade.school_id == school.id,
            Grade.name == "高一",
        )
    )
    grade = result.scalar_one_or_none()
    if grade is None:
        grade = Grade(school_id=school.id, name="高一", academic_year="2025-2026")
        session.add(grade)
        await session.flush()

    # Class
    result = await session.execute(
        select(Class).where(
            Class.grade_id == grade.id,
            Class.name == "高一(3)班",
        )
    )
    class_ = result.scalar_one_or_none()
    if class_ is None:
        class_ = Class(
            grade_id=grade.id,
            name="高一(3)班",
            stage="高中",
            subject="化学",
            student_count=0,
        )
        session.add(class_)
        await session.flush()

    # Demo Teacher Account + Teacher profile
    result = await session.execute(
        select(Account).where(Account.phone == "13800000000")
    )
    account = result.scalar_one_or_none()
    if account is None:
        account = Account(
            phone="13800000000",
            password_hash=hash_password("demo123456"),
            role=AccountRole.teacher,
        )
        session.add(account)
        await session.flush()

    result = await session.execute(
        select(Teacher).where(Teacher.account_id == account.id)
    )
    teacher = result.scalar_one_or_none()
    if teacher is None:
        teacher = Teacher(
            account_id=account.id,
            school_id=school.id,
            name="张老师（演示）",
            status=TeacherAccountStatus.approved,
            role=TeacherRole.teacher,
        )
        session.add(teacher)
        await session.flush()

    # TeacherClassSubject
    result = await session.execute(
        select(TeacherClassSubject).where(
            TeacherClassSubject.teacher_id == teacher.id,
            TeacherClassSubject.class_id == class_.id,
        )
    )
    tcs = result.scalar_one_or_none()
    if tcs is None:
        tcs = TeacherClassSubject(
            teacher_id=teacher.id,
            class_id=class_.id,
            subject="化学",
            is_head_teacher=True,
        )
        session.add(tcs)

    await session.commit()
    return school, grade, class_, teacher


async def seed_barrier_config(session, teacher: Teacher) -> BarrierConfig | None:
    """Create default barrier config for teacher if not exists."""
    result = await session.execute(
        select(BarrierConfig).where(BarrierConfig.teacher_id == teacher.id)
    )
    config = result.scalar_one_or_none()
    if config is None:
        config = BarrierConfig(teacher_id=teacher.id)
        session.add(config)
        await session.commit()
    return config


async def seed_historical_exams(session) -> int:
    """Seed sample historical exam questions. Returns count created."""
    count = 0
    for exam in DEMO_HISTORICAL_EXAMS:
        exists = await session.execute(
            select(HistoricalExam).where(
                HistoricalExam.source == exam["source"],
                HistoricalExam.year == exam["year"],
                HistoricalExam.question_number == exam["question_number"],
            )
        )
        if exists.scalar_one_or_none() is None:
            session.add(HistoricalExam(**exam))
            count += 1
    if count:
        await session.commit()
    return count


async def seed_all() -> dict:
    """Run all seed tasks. Returns summary dict."""
    summary = {}
    async with MainSession() as session:
        # Knowledge points
        kp_count = await seed_knowledge_points(session)
        summary["knowledge_points_created"] = kp_count

        # Demo org
        school, grade, class_, teacher = await seed_demo_org(session)
        summary["school"] = school.name
        summary["grade"] = grade.name
        summary["class"] = class_.name
        summary["teacher"] = teacher.name

        # Barrier config
        config = await seed_barrier_config(session, teacher)
        summary["barrier_config"] = "created" if config else "exists"

        # Historical exams
        exam_count = await seed_historical_exams(session)
        summary["historical_exams_created"] = exam_count

    return summary


def main():
    """CLI entry point."""
    print("Seeding ChemAI database...")
    summary = asyncio.run(seed_all())
    print()
    for key, value in summary.items():
        print(f"  {key}: {value}")
    print()
    print("Seed complete.")


if __name__ == "__main__":
    main()
