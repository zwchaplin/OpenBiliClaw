"""OpenClaw integration adapter package."""

from .bootstrap import (
    OpenClawAdapterServices,
    build_openclaw_adapter,
    build_openclaw_adapter_services,
)
from .errors import (
    AdapterInitializationError,
    AdapterOperationError,
    AdapterValidationError,
    OpenClawAdapterError,
)
from .operations import OpenClawAdapter
from .schemas import (
    DelightItem,
    DelightResponse,
    FeedbackRequest,
    FeedbackResponse,
    ProfileResponse,
    RecommendationItem,
    RecommendationResponse,
    RuntimeStatusResponse,
    SyncAccountResponse,
)
from .skill import OpenClawSkillDescriptor, build_openclaw_skills

__all__ = [
    "AdapterInitializationError",
    "AdapterOperationError",
    "AdapterValidationError",
    "build_openclaw_adapter",
    "build_openclaw_adapter_services",
    "build_openclaw_skills",
    "DelightItem",
    "DelightResponse",
    "FeedbackRequest",
    "FeedbackResponse",
    "OpenClawAdapter",
    "OpenClawAdapterServices",
    "OpenClawAdapterError",
    "OpenClawSkillDescriptor",
    "ProfileResponse",
    "RecommendationItem",
    "RecommendationResponse",
    "RuntimeStatusResponse",
    "SyncAccountResponse",
]
