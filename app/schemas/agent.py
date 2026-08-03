"""Agent schemas — SSE events, conversation, memory.

Aligned with 35-API §10 (agent/conversation/routing/memory routers), §4 (SSE protocol).
"""

from pydantic import BaseModel, Field


# ── Agent chat request (35号 §三: POST /api/agent/chat/langgraph/stream) ──
class AgentChatRequest(BaseModel):
    message: str
    thread_id: str
    context: dict = Field(
        default_factory=lambda: {"user_id": 0, "role": "teacher"}
    )


# ── SSE event types (35号 §四) ─────────────────────────────
class SSEPhaseEvent(BaseModel):
    event: str = "phase"
    data: dict  # {phase: thinking|reply|awaiting_approval}


class SSEToolCallEvent(BaseModel):
    event: str = "tool_call"
    data: dict  # {name, args}


class SSEToolResultEvent(BaseModel):
    event: str = "tool_result"
    data: dict  # {name, success, result}


class SSETextEvent(BaseModel):
    event: str = "text"
    data: dict  # {content}


class SSEComponentEvent(BaseModel):
    event: str = "component"
    data: dict  # {component, params}


class SSEDoneEvent(BaseModel):
    event: str = "done"
    data: dict  # {thread_id, tool_calls}


# ── Conversation ───────────────────────────────────────────
class ConversationCreate(BaseModel):
    thread_id: str = Field(..., max_length=100)
    student_id: int | None = None


class ConversationRead(BaseModel):
    id: int
    thread_id: str
    student_id: int | None
    created_at: str


class ConversationDelete(BaseModel):
    thread_id: str


# ── Memory ─────────────────────────────────────────────────
class MemoryRead(BaseModel):
    id: int
    student_id: int | None
    teacher_id: int | None
    memory_type: str
    content: dict
    created_at: str
    updated_at: str
