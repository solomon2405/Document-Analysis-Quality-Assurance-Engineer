from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


RiskLevel = Literal["Low", "Medium", "High"]
LayerType = Literal["lexical", "semantic", "structural", "numeric", "ocr"]


class Location(BaseModel):
    file: str = ""
    page: int = 1
    paragraph: int = 1


class LayerMismatch(BaseModel):
    layer: LayerType
    change_type: str
    input_text: str = ""
    output_text: str = ""
    location: Location
    context_window: str = ""
    confidence_score: float = Field(ge=0, le=1)
    risk_level: RiskLevel = "Low"


class EntityDiffRow(BaseModel):
    entity_type: str
    input_value: str
    output_value: str
    status: str


class ComparisonResponse(BaseModel):
    overall_similarity_score: float = Field(ge=0, le=100)
    structural_similarity: float = Field(ge=0, le=100)
    semantic_similarity: float = Field(ge=0, le=100)
    risk_assessment: RiskLevel
    critical_changes: list[str]
    mismatches: list[LayerMismatch]
    summary_explanation: str
    entity_comparison: list[EntityDiffRow] = []
    stage_progress: dict[str, int] = {}
    audit_log: list[str] = []


class JobCreateResponse(BaseModel):
    job_id: str
    status: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: Literal["queued", "processing", "completed", "failed"]
    stage_progress: dict[str, int]
    error: str | None = None
    result: ComparisonResponse | None = None
