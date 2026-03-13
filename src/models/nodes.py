from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ModuleNode(BaseModel):
    path: str
    language: str
    purpose_statement: Optional[str] = None
    domain_cluster: Optional[str] = None
    complexity_score: Optional[float] = None
    change_velocity_30d: Optional[float] = None
    is_dead_code_candidate: bool = False
    last_modified: Optional[datetime] = None


class DatasetNode(BaseModel):
    name: str
    storage_type: Literal["table", "file", "stream", "api"]
    schema_snapshot: Optional[dict] = None
    freshness_sla: Optional[str] = None
    owner: Optional[str] = None
    is_source_of_truth: Optional[bool] = None


class FunctionNode(BaseModel):
    qualified_name: str
    parent_module: str
    signature: str
    purpose_statement: Optional[str] = None
    call_count_within_repo: Optional[int] = None
    is_public_api: bool = False


class TransformationNode(BaseModel):
    id: str = Field(..., description="Stable identifier for transformation instance")
    source_datasets: list[str] = Field(default_factory=list)
    target_datasets: list[str] = Field(default_factory=list)
    transformation_type: str
    source_file: str
    line_range: tuple[int, int] | None = None
    sql_query_if_applicable: Optional[str] = None


class ConfigNode(BaseModel):
    path: str
    kind: str  # e.g. "dbt_schema", "airflow", "prefect", "unknown"
    purpose_statement: Optional[str] = None
