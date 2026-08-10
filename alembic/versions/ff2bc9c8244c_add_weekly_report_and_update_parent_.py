"""add_weekly_report_and_update_parent_notification

Revision ID: ff2bc9c8244c
Revises: d5ad215c62d9
Create Date: 2026-08-09 21:19:56.668054
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ff2bc9c8244c'
down_revision: Union[str, None] = 'd5ad215c62d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 新建 weekly_report 表
    op.create_table('weekly_report',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('student_id', sa.Integer(), nullable=False, comment='学生'),
    sa.Column('week_start', sa.DateTime(), nullable=False, comment='本周一日期'),
    sa.Column('week_end', sa.DateTime(), nullable=False, comment='本周日日期'),
    sa.Column('summary', sa.String(length=200), nullable=False, comment='概述段（≤60字）'),
    sa.Column('detail', sa.Text(), nullable=False, comment='具体表现段（≤120字）'),
    sa.Column('advice', sa.Text(), nullable=False, comment='家庭建议段（≤80字）'),
    sa.Column('no_data', sa.Boolean(), server_default='0', nullable=False, comment='当周无数据时为 True'),
    sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False, comment='生成时间'),
    sa.Column('generated_by', sa.String(length=20), nullable=False, comment='生成方式：auto / manual'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False, comment='记录创建时间'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False, comment='记录最后更新时间'),
    sa.ForeignKeyConstraint(['student_id'], ['student.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('student_id', 'week_start', name='uq_weekly_report_student_week')
    )

    # 2. ParentNotification 字段迁移：is_read(bool) → read_at(datetime) + 新增 related_id
    #    必须先加列 → 数据迁移 → 再删旧列（SQLite batch_alter_table 在三步之间才能正确执行）
    with op.batch_alter_table('parent_notification', schema=None) as batch_op:
        batch_op.add_column(sa.Column('read_at', sa.DateTime(timezone=True), nullable=True, comment='已读时间'))
        batch_op.add_column(sa.Column('related_id', sa.Integer(), nullable=True, comment='关联资源 ID（如 weekly_report_id / warning_log_id）'))

    # 数据迁移：新表中已读的 is_read=1 → read_at=created_at
    op.execute(
        "UPDATE parent_notification SET read_at = created_at WHERE is_read = 1"
    )

    with op.batch_alter_table('parent_notification', schema=None) as batch_op:
        batch_op.drop_column('is_read')


def downgrade() -> None:
    with op.batch_alter_table('parent_notification', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_read', sa.BOOLEAN(), server_default=sa.text("'0'"), nullable=False))

    # 反向数据迁移
    op.execute(
        "UPDATE parent_notification SET is_read = 1 WHERE read_at IS NOT NULL"
    )

    with op.batch_alter_table('parent_notification', schema=None) as batch_op:
        batch_op.drop_column('read_at')
        batch_op.drop_column('related_id')

    op.drop_table('weekly_report')
