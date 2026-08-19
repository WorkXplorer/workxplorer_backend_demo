from .choices import ApplicationDocumentTypes, ApplicationStatus
from .applications import ApplicationDocument, JobApplication
from .status import (
    StatusCategory,
    ApplicationStatusModel,
    StatusTemplate,
)
from .ai_evaluation import ApplicationAIEvaluation, EvaluationStatus
from .report_snapshot import DailyReportSnapshot

__all__ = [
    # Legacy choices (kept for backward compatibility during migration)
    "ApplicationStatus",
    "ApplicationDocumentTypes",
    # Models
    "ApplicationDocument",
    "JobApplication",
    # Flexible status system
    "StatusCategory",
    "ApplicationStatusModel",
    "StatusTemplate",
    # AI Evaluation
    "ApplicationAIEvaluation",
    "EvaluationStatus",
    # Reporting history
    "DailyReportSnapshot",
]
