"""add_learning_plan_and_notification_tables

Revision ID: d5ad215c62d9
Revises: bb6ed1611c14
Create Date: 2026-08-09 17:35:22.858121
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5ad215c62d9'
down_revision: Union[str, None] = 'bb6ed1611c14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('learning_plan',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('student_id', sa.Integer(), nullable=False, comment='学生'),
    sa.Column('title', sa.String(length=200), nullable=False, comment='计划标题'),
    sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False, comment='是否为当前活跃计划'),
    sa.Column('created_by', sa.String(length=50), nullable=True, comment='创建来源：teacher / agent'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False, comment='记录创建时间'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False, comment='记录最后更新时间'),
    sa.ForeignKeyConstraint(['student_id'], ['student.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('notification',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('student_id', sa.Integer(), nullable=False, comment='接收学生'),
    sa.Column('type', sa.String(length=30), nullable=False, comment='通知类型：practice_assigned / plan_updated / report_ready'),
    sa.Column('title', sa.String(length=200), nullable=False, comment='通知标题'),
    sa.Column('body', sa.Text(), nullable=False, comment='通知正文'),
    sa.Column('related_id', sa.Integer(), nullable=True, comment='关联资源 ID（如 practice_id / plan_id）'),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True, comment='已读时间'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False, comment='记录创建时间'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False, comment='记录最后更新时间'),
    sa.ForeignKeyConstraint(['student_id'], ['student.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('learning_plan_task',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('plan_id', sa.Integer(), nullable=False, comment='所属计划'),
    sa.Column('day_number', sa.Integer(), nullable=False, comment='第几天（从 1 开始）'),
    sa.Column('task_description', sa.Text(), nullable=False, comment='任务描述'),
    sa.Column('estimated_minutes', sa.Integer(), nullable=False, comment='预估完成时间（分钟）'),
    sa.Column('knowledge_points', sa.JSON(), nullable=True, comment='关联知识点标签数组'),
    sa.Column('status', sa.String(length=20), server_default='pending', nullable=False, comment='任务状态：pending / completed / skipped'),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True, comment='完成时间'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False, comment='记录创建时间'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False, comment='记录最后更新时间'),
    sa.ForeignKeyConstraint(['plan_id'], ['learning_plan.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('learning_plan_task')
    op.drop_table('notification')
    op.drop_table('learning_plan')
