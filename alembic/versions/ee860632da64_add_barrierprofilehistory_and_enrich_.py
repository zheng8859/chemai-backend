"""add BarrierProfileHistory and enrich WarningLog with status lifecycle fields

Revision ID: ee860632da64
Revises: 48462f130944
Create Date: 2026-08-07 21:59:28.890511
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ee860632da64'
down_revision: Union[str, None] = '48462f130944'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # BarrierProfileHistory 新表
    op.create_table('barrier_profile_history',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('student_id', sa.Integer(), nullable=False, comment='学生 ID'),
    sa.Column('snapshot_at', sa.DateTime(timezone=True), nullable=False, comment='快照时间'),
    sa.Column('profile', sa.JSON(), nullable=False, comment='三维障碍分布 JSON'),
    sa.Column('dominant_barrier', sa.String(length=20), nullable=True, comment='主导障碍类型：concept / reading / expression'),
    sa.ForeignKeyConstraint(['student_id'], ['student.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    # WarningLog 新增 6 列
    with op.batch_alter_table('warning_log', schema=None) as batch_op:
        batch_op.add_column(sa.Column('title', sa.String(length=200), server_default='', nullable=False, comment='预警标题（人类可读摘要）'))
        batch_op.add_column(sa.Column('data', sa.JSON(), nullable=True, comment='预警数据快照 JSON'))
        batch_op.add_column(sa.Column('status', sa.String(length=20), server_default='pending', nullable=False, comment='预警状态：pending / processing / resolved / dismissed'))
        batch_op.add_column(sa.Column('processed_by', sa.Integer(), nullable=True, comment='处理人（教师 ID）'))
        batch_op.add_column(sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True, comment='处理时间'))
        batch_op.add_column(sa.Column('note', sa.Text(), nullable=True, comment='教师备注'))


def downgrade() -> None:
    with op.batch_alter_table('warning_log', schema=None) as batch_op:
        batch_op.drop_column('note')
        batch_op.drop_column('processed_at')
        batch_op.drop_column('processed_by')
        batch_op.drop_column('status')
        batch_op.drop_column('data')
        batch_op.drop_column('title')

    op.drop_table('barrier_profile_history')
