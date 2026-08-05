"""User service — 账户列表、教师申请审批、学生/家长管理、任课分配。

多租户数据隔离核心：verify_school_access 校验 class/grade 是否属于当前学校。
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from ..core.enums import (
    AccountRole,
    TeacherAccountStatus,
    ApplicationStatus,
    StudentStatus,
)
from ..models.user import (
    Account,
    Teacher,
    Student,
    Parent,
    TeacherClassSubject,
    TeacherApplication,
)
from ..models.org import Class, Grade, School
from ..schemas.user import (
    AccountRead,
    TeacherRead,
    TeacherUpdate,
    StudentRead,
    StudentUpdate,
    ParentRead,
    ParentUpdate,
    TeacherClassSubjectRead,
    TeacherClassSubjectCreate,
    TeacherApplicationRead,
)


class UserError(Exception):
    """用户相关业务错误。"""

    def __init__(self, detail: str, error_code: str = "RESOURCE_NOT_FOUND"):
        self.detail = detail
        self.error_code = error_code
        super().__init__(detail)


class UserService:
    """用户管理服务。"""

    # ═══════════════════════════════════════════════════════════
    # Account
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def list_accounts(
        db: AsyncSession,
        limit: int = 20,
        offset: int = 0,
        role: str | None = None,
    ) -> tuple[list[dict], int]:
        query = select(Account)
        count_query = select(func.count(Account.id))

        if role:
            query = query.where(Account.role == role)
            count_query = count_query.where(Account.role == role)

        total = (await db.execute(count_query)).scalar() or 0
        result = await db.execute(
            query.order_by(Account.created_at.desc()).offset(offset).limit(limit)
        )
        accounts = [{
            "id": a.id,
            "phone": a.phone,
            "role": str(a.role),
            "created_at": a.created_at.isoformat(),
        } for a in result.scalars().all()]
        return accounts, total

    # ═══════════════════════════════════════════════════════════
    # Teacher Application
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_teacher_applications(
        db: AsyncSession,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[TeacherApplicationRead], int]:
        query = select(TeacherApplication)
        count_query = select(func.count(TeacherApplication.id))

        if status:
            query = query.where(TeacherApplication.status == status)
            count_query = count_query.where(TeacherApplication.status == status)

        total = (await db.execute(count_query)).scalar() or 0
        result = await db.execute(
            query.order_by(TeacherApplication.created_at.desc()).offset(offset).limit(limit)
        )
        apps = [TeacherApplicationRead.model_validate(a) for a in result.scalars().all()]
        return apps, total

    @staticmethod
    async def approve_teacher_application(
        db: AsyncSession, application_id: int, reviewer_id: int, approved: bool
    ) -> TeacherApplicationRead:
        result = await db.execute(
            select(TeacherApplication).where(TeacherApplication.id == application_id)
        )
        app = result.scalar_one_or_none()
        if app is None:
            raise UserError(f"申请不存在: id={application_id}")

        if app.status != ApplicationStatus.pending:
            raise UserError("申请已处理", "ALREADY_PROCESSED")

        from datetime import datetime, timezone

        if approved:
            app.status = ApplicationStatus.approved
            # Update teacher account status to approved
            result = await db.execute(
                select(Teacher).where(
                    Teacher.account_id == select(Account.id).where(
                        Account.phone == app.phone
                    ).scalar_subquery()
                )
            )
            teacher = result.scalar_one_or_none()
            if teacher:
                teacher.status = TeacherAccountStatus.approved
        else:
            app.status = ApplicationStatus.rejected

        app.reviewer_id = reviewer_id
        app.reviewed_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(app)
        return TeacherApplicationRead.model_validate(app)

    @staticmethod
    async def reject_teacher_application(
        db: AsyncSession, application_id: int, reviewer_id: int
    ) -> TeacherApplicationRead:
        return await UserService.approve_teacher_application(
            db, application_id, reviewer_id, approved=False
        )

    # ═══════════════════════════════════════════════════════════
    # Student
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def create_student(
        db: AsyncSession, class_id: int, name: str, student_id: str,
        school_id: int | None = None,
    ) -> StudentRead:
        # Resolve school_id from class if not provided
        if school_id is None:
            cls_result = await db.execute(select(Class).where(Class.id == class_id))
            cls = cls_result.scalar_one_or_none()
            if cls is None:
                raise UserError(f"班级不存在: id={class_id}")
            grade_result = await db.execute(select(Grade).where(Grade.id == cls.grade_id))
            grade = grade_result.scalar_one_or_none()
            if grade is None:
                raise UserError(f"年级不存在: id={cls.grade_id}")
            school_id = grade.school_id

        # Create account
        account = Account(
            phone="",
            password_hash="$2b$12$placeholder",  # 未激活，占位密码
            role=AccountRole.student,
        )
        db.add(account)
        await db.flush()

        student = Student(
            account_id=account.id,
            class_id=class_id,
            school_id=school_id,
            name=name,
            student_id=student_id,
            is_activated=False,
            status=StudentStatus.approved,
        )
        db.add(student)
        await db.commit()
        await db.refresh(student)
        return StudentRead.model_validate(student)

    @staticmethod
    async def get_student(db: AsyncSession, student_id: int) -> StudentRead:
        result = await db.execute(select(Student).where(Student.id == student_id))
        student = result.scalar_one_or_none()
        if student is None:
            raise UserError(f"学生不存在: id={student_id}")
        return StudentRead.model_validate(student)

    @staticmethod
    async def list_students_by_class(
        db: AsyncSession, class_id: int,
        limit: int = 20, offset: int = 0,
    ) -> tuple[list[StudentRead], int]:
        total = (await db.execute(
            select(func.count(Student.id)).where(Student.class_id == class_id)
        )).scalar() or 0

        result = await db.execute(
            select(Student)
            .where(Student.class_id == class_id)
            .order_by(Student.name)
            .offset(offset).limit(limit)
        )
        students = [StudentRead.model_validate(s) for s in result.scalars().all()]
        return students, total

    @staticmethod
    async def update_student(
        db: AsyncSession, student_id: int, data: StudentUpdate,
    ) -> StudentRead:
        result = await db.execute(select(Student).where(Student.id == student_id))
        student = result.scalar_one_or_none()
        if student is None:
            raise UserError(f"学生不存在: id={student_id}")

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(student, key, value)
        await db.commit()
        await db.refresh(student)
        return StudentRead.model_validate(student)

    @staticmethod
    async def delete_student(db: AsyncSession, student_id: int) -> None:
        result = await db.execute(select(Student).where(Student.id == student_id))
        student = result.scalar_one_or_none()
        if student is None:
            raise UserError(f"学生不存在: id={student_id}")
        await db.delete(student)
        await db.commit()

    @staticmethod
    async def get_student_profile(
        db: AsyncSession, account_id: int,
    ) -> StudentRead:
        """学生通过自己的 account_id 获取 Profile。"""
        result = await db.execute(
            select(Student).where(Student.account_id == account_id)
        )
        student = result.scalar_one_or_none()
        if student is None:
            raise UserError(f"学生不存在: account_id={account_id}")
        return StudentRead.model_validate(student)

    # ═══════════════════════════════════════════════════════════
    # Parent
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def create_parent(
        db: AsyncSession, name: str, phone: str,
    ) -> ParentRead:
        account = Account(phone=phone, password_hash="", role=AccountRole.parent)
        db.add(account)
        await db.flush()

        parent = Parent(account_id=account.id, name=name)
        db.add(parent)
        await db.commit()
        await db.refresh(parent)
        return ParentRead.model_validate(parent)

    @staticmethod
    async def get_parent(db: AsyncSession, parent_id: int) -> ParentRead:
        result = await db.execute(select(Parent).where(Parent.id == parent_id))
        parent = result.scalar_one_or_none()
        if parent is None:
            raise UserError(f"家长不存在: id={parent_id}")
        return ParentRead.model_validate(parent)

    @staticmethod
    async def update_parent(
        db: AsyncSession, parent_id: int, data: ParentUpdate,
    ) -> ParentRead:
        result = await db.execute(select(Parent).where(Parent.id == parent_id))
        parent = result.scalar_one_or_none()
        if parent is None:
            raise UserError(f"家长不存在: id={parent_id}")
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(parent, key, value)
        await db.commit()
        await db.refresh(parent)
        return ParentRead.model_validate(parent)

    @staticmethod
    async def list_parents(
        db: AsyncSession, limit: int = 20, offset: int = 0,
    ) -> tuple[list[ParentRead], int]:
        total = (await db.execute(select(func.count(Parent.id)))).scalar() or 0
        result = await db.execute(
            select(Parent).order_by(Parent.name).offset(offset).limit(limit)
        )
        parents = [ParentRead.model_validate(p) for p in result.scalars().all()]
        return parents, total

    # ═══════════════════════════════════════════════════════════
    # Teacher Assignment
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def create_assignment(
        db: AsyncSession, data: TeacherClassSubjectCreate,
    ) -> TeacherClassSubjectRead:
        tcs = TeacherClassSubject(
            teacher_id=data.teacher_id,
            class_id=data.class_id,
            subject=data.subject,
            is_head_teacher=data.is_head_teacher,
        )
        db.add(tcs)
        await db.commit()
        await db.refresh(tcs)
        return TeacherClassSubjectRead.model_validate(tcs)

    @staticmethod
    async def list_teacher_assignments(
        db: AsyncSession, teacher_id: int,
    ) -> list[TeacherClassSubjectRead]:
        result = await db.execute(
            select(TeacherClassSubject).where(
                TeacherClassSubject.teacher_id == teacher_id
            )
        )
        return [TeacherClassSubjectRead.model_validate(t) for t in result.scalars().all()]

    @staticmethod
    async def delete_assignment(db: AsyncSession, assignment_id: int) -> None:
        result = await db.execute(
            select(TeacherClassSubject).where(TeacherClassSubject.id == assignment_id)
        )
        tcs = result.scalar_one_or_none()
        if tcs is None:
            raise UserError(f"任课关系不存在: id={assignment_id}")
        await db.delete(tcs)
        await db.commit()

    # ═══════════════════════════════════════════════════════════
    # School Access Helper
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def verify_school_access(
        db: AsyncSession, class_id: int | None, grade_id: int | None,
        user_school_id: int,
    ) -> bool:
        """验证 class_id 或 grade_id 属于 user 的学校。"""
        if class_id:
            result = await db.execute(select(Class).where(Class.id == class_id))
            cls = result.scalar_one_or_none()
            if cls is None:
                raise UserError(f"班级不存在: id={class_id}")
            grade_id = cls.grade_id

        result = await db.execute(select(Grade).where(Grade.id == grade_id))
        grade = result.scalar_one_or_none()
        if grade is None:
            raise UserError(f"年级不存在: id={grade_id}")

        if grade.school_id != user_school_id:
            raise UserError("无权访问其他学校的数据", "PERMISSION_DENIED")
        return True
