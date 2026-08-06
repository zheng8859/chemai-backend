"""Org service — 学校/年级/班级 CRUD + 组织树。

多租户数据隔离：所有查询沿 school→grade→class 链路过滤。
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from ..models.org import School, Grade, Class
from ..schemas.org import (
    SchoolCreate,
    SchoolRead,
    SchoolUpdate,
    GradeCreate,
    GradeRead,
    GradeUpdate,
    ClassCreate,
    ClassRead,
    ClassUpdate,
)


class OrgError(Exception):
    """组织相关业务错误。"""

    def __init__(self, detail: str, error_code: str = "RESOURCE_NOT_FOUND"):
        self.detail = detail
        self.error_code = error_code
        super().__init__(detail)


class OrgService:
    """组织链服务。所有方法均为静态方法，接收 AsyncSession。"""

    # ═══════════════════════════════════════════════════════════
    # School
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def create_school(db: AsyncSession, data: SchoolCreate) -> SchoolRead:
        school = School(**data.model_dump())
        db.add(school)
        await db.commit()
        await db.refresh(school)
        return SchoolRead.model_validate(school)

    @staticmethod
    async def get_school(db: AsyncSession, school_id: int) -> SchoolRead:
        result = await db.execute(select(School).where(School.id == school_id))
        school = result.scalar_one_or_none()
        if school is None:
            raise OrgError(f"学校不存在: id={school_id}")
        return SchoolRead.model_validate(school)

    @staticmethod
    async def list_schools(
        db: AsyncSession,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[SchoolRead], int]:
        total_query = select(func.count(School.id))
        total = (await db.execute(total_query)).scalar() or 0

        query = (
            select(School)
            .order_by(School.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(query)
        schools = [SchoolRead.model_validate(s) for s in result.scalars().all()]
        return schools, total

    @staticmethod
    async def update_school(
        db: AsyncSession, school_id: int, data: SchoolUpdate
    ) -> SchoolRead:
        result = await db.execute(select(School).where(School.id == school_id))
        school = result.scalar_one_or_none()
        if school is None:
            raise OrgError(f"学校不存在: id={school_id}")

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(school, key, value)
        await db.commit()
        await db.refresh(school)
        return SchoolRead.model_validate(school)

    @staticmethod
    async def delete_school(db: AsyncSession, school_id: int) -> None:
        result = await db.execute(select(School).where(School.id == school_id))
        school = result.scalar_one_or_none()
        if school is None:
            raise OrgError(f"学校不存在: id={school_id}")
        await db.delete(school)
        await db.commit()

    # ═══════════════════════════════════════════════════════════
    # Grade
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def create_grade(db: AsyncSession, data: GradeCreate) -> GradeRead:
        # 验证学校存在
        result = await db.execute(select(School).where(School.id == data.school_id))
        if result.scalar_one_or_none() is None:
            raise OrgError(f"学校不存在: id={data.school_id}")

        grade = Grade(**data.model_dump())
        db.add(grade)
        await db.commit()
        await db.refresh(grade)
        return GradeRead.model_validate(grade)

    @staticmethod
    async def get_grade(db: AsyncSession, grade_id: int) -> GradeRead:
        result = await db.execute(select(Grade).where(Grade.id == grade_id))
        grade = result.scalar_one_or_none()
        if grade is None:
            raise OrgError(f"年级不存在: id={grade_id}")
        return GradeRead.model_validate(grade)

    @staticmethod
    async def list_grades_by_school(
        db: AsyncSession,
        school_id: int,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[GradeRead], int]:
        # 验证学校存在
        result = await db.execute(select(School).where(School.id == school_id))
        if result.scalar_one_or_none() is None:
            raise OrgError(f"学校不存在: id={school_id}")

        total_query = select(func.count(Grade.id)).where(Grade.school_id == school_id)
        total = (await db.execute(total_query)).scalar() or 0

        query = (
            select(Grade)
            .where(Grade.school_id == school_id)
            .order_by(Grade.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(query)
        grades = [GradeRead.model_validate(g) for g in result.scalars().all()]
        return grades, total

    @staticmethod
    async def update_grade(
        db: AsyncSession, grade_id: int, data: GradeUpdate
    ) -> GradeRead:
        result = await db.execute(select(Grade).where(Grade.id == grade_id))
        grade = result.scalar_one_or_none()
        if grade is None:
            raise OrgError(f"年级不存在: id={grade_id}")

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(grade, key, value)
        await db.commit()
        await db.refresh(grade)
        return GradeRead.model_validate(grade)

    @staticmethod
    async def delete_grade(db: AsyncSession, grade_id: int) -> None:
        result = await db.execute(select(Grade).where(Grade.id == grade_id))
        grade = result.scalar_one_or_none()
        if grade is None:
            raise OrgError(f"年级不存在: id={grade_id}")
        await db.delete(grade)
        await db.commit()

    # ═══════════════════════════════════════════════════════════
    # Class
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def create_class(db: AsyncSession, data: ClassCreate) -> ClassRead:
        # 验证年级存在
        result = await db.execute(select(Grade).where(Grade.id == data.grade_id))
        if result.scalar_one_or_none() is None:
            raise OrgError(f"年级不存在: id={data.grade_id}")

        cls = Class(**data.model_dump())
        db.add(cls)
        await db.commit()
        await db.refresh(cls)
        return ClassRead.model_validate(cls)

    @staticmethod
    async def get_class(db: AsyncSession, class_id: int) -> ClassRead:
        result = await db.execute(select(Class).where(Class.id == class_id))
        cls = result.scalar_one_or_none()
        if cls is None:
            raise OrgError(f"班级不存在: id={class_id}")
        return ClassRead.model_validate(cls)

    @staticmethod
    async def list_classes_by_grade(
        db: AsyncSession,
        grade_id: int,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[ClassRead], int]:
        # 验证年级存在
        result = await db.execute(select(Grade).where(Grade.id == grade_id))
        if result.scalar_one_or_none() is None:
            raise OrgError(f"年级不存在: id={grade_id}")

        total_query = select(func.count(Class.id)).where(Class.grade_id == grade_id)
        total = (await db.execute(total_query)).scalar() or 0

        query = (
            select(Class)
            .where(Class.grade_id == grade_id)
            .order_by(Class.name)
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(query)
        classes = [ClassRead.model_validate(c) for c in result.scalars().all()]
        return classes, total

    @staticmethod
    async def update_class(
        db: AsyncSession, class_id: int, data: ClassUpdate
    ) -> ClassRead:
        result = await db.execute(select(Class).where(Class.id == class_id))
        cls = result.scalar_one_or_none()
        if cls is None:
            raise OrgError(f"班级不存在: id={class_id}")

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(cls, key, value)
        await db.commit()
        await db.refresh(cls)
        return ClassRead.model_validate(cls)

    @staticmethod
    async def delete_class(db: AsyncSession, class_id: int) -> None:
        result = await db.execute(select(Class).where(Class.id == class_id))
        cls = result.scalar_one_or_none()
        if cls is None:
            raise OrgError(f"班级不存在: id={class_id}")
        await db.delete(cls)
        await db.commit()

    # ═══════════════════════════════════════════════════════════
    # Org Tree
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_org_tree(
        db: AsyncSession, school_id: int | None = None
    ) -> list[dict]:
        """返回 school → grades → classes 嵌套 JSON 树。

        若指定 school_id 则只返回单校，否则返回所有学校。
        """
        school_query = select(School).options(
            selectinload(School.grades).selectinload(Grade.classes)
        )

        if school_id is not None:
            school_query = school_query.where(School.id == school_id)

        result = await db.execute(school_query)
        schools = result.scalars().all()

        tree = []
        for school in schools:
            school_node = {
                "id": school.id,
                "name": school.name,
                "region": school.region,
                "grades": [],
            }
            for grade in school.grades:
                grade_node = {
                    "id": grade.id,
                    "name": grade.name,
                    "academic_year": grade.academic_year,
                    "classes": [],
                }
                for cls in grade.classes:
                    grade_node["classes"].append({
                        "id": cls.id,
                        "name": cls.name,
                        "student_count": cls.student_count,
                        "stage": cls.stage,
                        "subject": cls.subject,
                    })
                school_node["grades"].append(grade_node)
            tree.append(school_node)

        return tree
