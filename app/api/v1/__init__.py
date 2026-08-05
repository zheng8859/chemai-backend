"""ChemAI v1 API — 聚合所有领域路由 + 认证路由到统一 v1_router。

挂载于 /api/v1 前缀，包含 8 个路由组:
- auth     : 登录/注册/刷新
- org      : 学校/年级/班级 CRUD
- user     : 教师审核/学生/家长/任课分配
- teaching : 考试/题目/作答/批改
- diagnosis: 障碍诊断/复习/预警/练习分配
- homework : 亲子绑定/通知/报告
- ocr      : 上传会话/OCR 任务/答题卡提交
- question_bank: 题库文件夹/题目集/历年真题
"""

from fastapi import APIRouter

v1_router = APIRouter(prefix="/api/v1")
