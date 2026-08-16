"""add_question_set_is_system_and_barrier_max_raw

补两个模型已声明但 DB 缺失的列（schema 漂移修复，验收 ISSUE-008 延伸）：

1. question_set.is_system — 系统预设文件夹标记（不可删除）
2. barrier_profile_history.max_raw — 快照时班级各障碍最大原始值（归一化基线）

Revision ID: a7f3e1c9d2b4
Revises: ff2bc9c8244c
Create Date: 2026-08-16 18:10:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7f3e1c9d2b4'
down_revision: Union[str, None] = 'ff2bc9c8244c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('question_set', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'is_system', sa.Boolean(), server_default='0', nullable=False,
            comment='是否为系统预设（预设文件夹不可删除）',
        ))

    with op.batch_alter_table('barrier_profile_history', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'max_raw', sa.JSON(), nullable=True,
            comment='快照时班级各障碍类型最大原始值，用于归一化基线对比',
        ))


def downgrade() -> None:
    with op.batch_alter_table('barrier_profile_history', schema=None) as batch_op:
        batch_op.drop_column('max_raw')

    with op.batch_alter_table('question_set', schema=None) as batch_op:
        batch_op.drop_column('is_system')
