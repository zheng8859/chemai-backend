"""Agent schemas — ChatRequest, SSE events, Conversation, Memory."""

import pytest
from pydantic import ValidationError

from app.schemas.agent import (
    AgentChatRequest,
    SSEPhaseEvent, SSEToolCallEvent, SSEToolResultEvent,
    SSETextEvent, SSEComponentEvent, SSEDoneEvent,
    ConversationCreate, ConversationRead, ConversationDelete,
    MemoryRead,
)


class TestAgentChatRequest:
    def test_default_context(self):
        r = AgentChatRequest(message="你好", thread_id="thread-001")
        assert r.message == "你好"
        assert r.context == {"user_id": 0, "role": "teacher"}

    def test_custom_context(self):
        r = AgentChatRequest(
            message="帮我出题", thread_id="thread-001",
            context={"user_id": 10, "role": "teacher", "school_id": 1},
        )
        assert r.context["user_id"] == 10


class TestSSEPhaseEvent:
    def test_valid(self):
        r = SSEPhaseEvent(data={"phase": "thinking"})
        assert r.event == "phase"
        assert r.data == {"phase": "thinking"}


class TestSSEToolCallEvent:
    def test_valid(self):
        r = SSEToolCallEvent(data={"name": "search_questions", "args": {"kp": "氧化还原"}})
        assert r.event == "tool_call"
        assert r.data["name"] == "search_questions"


class TestSSEToolResultEvent:
    def test_valid(self):
        r = SSEToolResultEvent(data={"name": "search_questions", "success": True, "result": []})
        assert r.event == "tool_result"
        assert r.data["success"] is True


class TestSSETextEvent:
    def test_valid(self):
        r = SSETextEvent(data={"content": "这是一段回复"})
        assert r.event == "text"
        assert r.data["content"] == "这是一段回复"


class TestSSEComponentEvent:
    def test_valid(self):
        r = SSEComponentEvent(data={"component": "QuestionCard", "params": {"id": 1}})
        assert r.event == "component"
        assert r.data["component"] == "QuestionCard"


class TestSSEDoneEvent:
    def test_valid(self):
        r = SSEDoneEvent(data={"thread_id": "t1", "tool_calls": 3})
        assert r.event == "done"
        assert r.data["tool_calls"] == 3


class TestConversationCreate:
    def test_valid(self):
        r = ConversationCreate(thread_id="thread-001")
        assert r.student_id is None

    def test_with_student(self):
        r = ConversationCreate(thread_id="thread-001", student_id=10)
        assert r.student_id == 10


class TestConversationRead:
    def test_valid(self):
        r = ConversationRead(id=1, thread_id="thread-001", student_id=None, created_at="2026-08-01T12:00:00")
        assert r.thread_id == "thread-001"


class TestConversationDelete:
    def test_valid(self):
        r = ConversationDelete(thread_id="thread-001")
        assert r.thread_id == "thread-001"


class TestMemoryRead:
    def test_valid(self):
        r = MemoryRead(
            id=1, student_id=10, teacher_id=None,
            memory_type="student_diagnosis_history",
            content={"barrier": "concept"},
            created_at="2026-08-01T12:00:00",
            updated_at="2026-08-01T12:00:00",
        )
        assert r.memory_type == "student_diagnosis_history"
        assert r.content == {"barrier": "concept"}
