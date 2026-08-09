"""补齐OCR模型字段

Revision ID: bb6ed1611c14
Revises: ee860632da64
Create Date: 2026-08-09 15:03:59.376595
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bb6ed1611c14'
down_revision: Union[str, None] = 'ee860632da64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── upload_session: 新增 10 字段 ──
    with op.batch_alter_table('upload_session', schema=None) as batch_op:
        batch_op.add_column(sa.Column('original_filename', sa.String(length=500), server_default='', nullable=False, comment='上传文件的原始文件名'))
        batch_op.add_column(sa.Column('mime_type', sa.String(length=50), server_default='', nullable=False, comment='文件的 MIME 类型'))
        batch_op.add_column(sa.Column('file_path', sa.String(length=500), server_default='', nullable=False, comment='文件存储的相对路径'))
        batch_op.add_column(sa.Column('detected_type', sa.String(length=20), server_default='', nullable=False, comment='自动检测的文件类型：PDF / IMAGE'))
        batch_op.add_column(sa.Column('ocr_result_json', sa.JSON(), nullable=True, comment='OCR 识别中间结果'))
        batch_op.add_column(sa.Column('grading_result_json', sa.JSON(), nullable=True, comment='批改结果汇总'))
        batch_op.add_column(sa.Column('total_pages', sa.Integer(), server_default='0', nullable=False, comment='总页数（PDF 多页）'))
        batch_op.add_column(sa.Column('completed_pages', sa.Integer(), server_default='0', nullable=False, comment='已完成识别页数'))
        batch_op.add_column(sa.Column('fallback_used', sa.Boolean(), server_default='0', nullable=False, comment='是否触发降级引擎'))
        batch_op.add_column(sa.Column('error_message', sa.Text(), nullable=True, comment='错误信息'))
        batch_op.add_column(sa.Column('version', sa.Integer(), server_default='1', nullable=False, comment='乐观锁版本号'))

    # ── ocr_task: 新增 9 字段 + teacher FK ──
    with op.batch_alter_table('ocr_task', schema=None) as batch_op:
        batch_op.add_column(sa.Column('teacher_id', sa.Integer(), nullable=False, server_default='1', comment='所属教师'))
        batch_op.add_column(sa.Column('image_path', sa.String(length=500), server_default='', nullable=False, comment='答题卡图片在磁盘上的路径'))
        batch_op.add_column(sa.Column('title', sa.String(length=200), server_default='', nullable=False, comment='任务标题（如文件名）'))
        batch_op.add_column(sa.Column('student_id_raw', sa.String(length=50), nullable=True, comment='OCR 提取的原始学号'))
        batch_op.add_column(sa.Column('student_name_raw', sa.String(length=50), nullable=True, comment='OCR 提取的原始姓名'))
        batch_op.add_column(sa.Column('progress', sa.Integer(), server_default='0', nullable=False, comment='处理进度百分比 0-100'))
        batch_op.add_column(sa.Column('confirmed', sa.Boolean(), server_default='0', nullable=False, comment='教师确认标记'))
        batch_op.add_column(sa.Column('error_message', sa.Text(), nullable=True, comment='错误描述（仅失败时）'))
        batch_op.add_column(sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True, comment='处理完成时间'))
        batch_op.create_foreign_key('fk_ocr_task_teacher_id', 'teacher', ['teacher_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    # ── ocr_task: 回退 ──
    with op.batch_alter_table('ocr_task', schema=None) as batch_op:
        batch_op.drop_constraint('fk_ocr_task_teacher_id', type_='foreignkey')
        batch_op.drop_column('completed_at')
        batch_op.drop_column('error_message')
        batch_op.drop_column('confirmed')
        batch_op.drop_column('progress')
        batch_op.drop_column('student_name_raw')
        batch_op.drop_column('student_id_raw')
        batch_op.drop_column('title')
        batch_op.drop_column('image_path')
        batch_op.drop_column('teacher_id')

    # ── upload_session: 回退 ──
    with op.batch_alter_table('upload_session', schema=None) as batch_op:
        batch_op.drop_column('version')
        batch_op.drop_column('error_message')
        batch_op.drop_column('fallback_used')
        batch_op.drop_column('completed_pages')
        batch_op.drop_column('total_pages')
        batch_op.drop_column('grading_result_json')
        batch_op.drop_column('ocr_result_json')
        batch_op.drop_column('detected_type')
        batch_op.drop_column('file_path')
        batch_op.drop_column('mime_type')
        batch_op.drop_column('original_filename')
