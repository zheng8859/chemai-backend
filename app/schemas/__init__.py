"""ChemAI Pydantic schemas — request/response models for all 11 API domains.

Aligned with 35-API Design document.
"""

from .base import SuccessResponse, PaginationParams, PaginatedResponse, ErrorResponse, ORMBase

from .auth import (
    LoginRequest,
    TeacherApplyRequest,
    ParentRegisterRequest,
    StudentBatchCreateRequest,
    TokenResponse,
    RefreshRequest,
)

from .user import (
    AccountRead,
    TeacherRead,
    TeacherUpdate,
    StudentRead,
    StudentUpdate,
    ParentRead,
    ParentUpdate,
    TeacherClassSubjectRead,
    TeacherClassSubjectCreate,
    TeacherApplicationCreate,
    TeacherApplicationRead,
    TeacherApplicationApprove,
)

from .org import (
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

from .teaching import (
    ExamCreate,
    ExamRead,
    ExamListParams,
    QuestionCreate,
    QuestionRead,
    QuestionGenerateRequest,
    QuestionGenerateResponse,
    QuestionHistoricalParams,
    StudentAnswerRead,
    PracticeSubmitRequest,
    GradingRunRequest,
    GradingRunResponse,
    ExamQuestionAssociateResponse,
    ExamPublishResponse,
    ExamFinalizeResponse,
    ExamQuestionItem,
    ExamQuestionsResponse,
    QuestionImportResponse,
)

from .diagnosis import (
    BarrierConfigRead,
    BarrierConfigUpdate,
    KnowledgePointRead,
    StudentDiagnosisItem,
    ClassDiagnosisResponse,
    ReviewTaskRead,
    ReviewCompleteRequest,
    WarningLogRead,
    WarningResolveRequest,
    PracticeAssignRequest,
    PracticeAssignResponse,
)

from .homework import (
    BindingCreate,
    BindingRead,
    ParentNotificationRead,
    ParentNotificationListParams,
    ReportSendRequest,
    ReportSendResponse,
    WeeklyReportRead,
)

from .ocr import (
    UploadSessionRead,
    BatchUploadRequest,
    BatchUploadResponse,
    StudentSubmissionRead,
    OCRTaskRead,
)

from .question_bank import (
    QuestionSetCreate,
    QuestionSetRead,
    QuestionSetItemRead,
    QuestionSetItemAdd,
    HistoricalExamRead,
)

from .agent import (
    AgentChatRequest,
    ConversationCreate,
    ConversationRead,
    ConversationDelete,
    MemoryRead,
)

from .parent import (
    BindCodeRequest,
    BindRequest,
    ChildInfo,
    ChildOverviewResponse,
    WeeklyTimelineItem,
    ChildTimelineResponse,
    WeeklyReportResponse,
    WeeklyReportGenerateRequest,
    ParentNotificationResponse,
    ParentAgentRequest,
)
