from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class EdgeType(str, Enum):
    IMPORTS = "IMPORTS"
    PRODUCES = "PRODUCES"
    CONSUMES = "CONSUMES"
    CALLS = "CALLS"
    CONFIGURES = "CONFIGURES"


class EdgeModel(BaseModel):
    """
    Typed representation of an edge in the knowledge graph.
    Used primarily for validation and documentation; the NetworkX
    storage layer stores attributes in a compatible dict form.
    """

    source: str
    target: str
    edge_type: EdgeType
    attrs: dict[str, Any] = Field(default_factory=dict)


class CartographyRunSummary(BaseModel):
    repo_root: str
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    module_count: int = 0
    module_edge_count: int = 0
    dataset_count: int = 0
    lineage_edge_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)

    @field_validator("module_count", "module_edge_count", "dataset_count", "lineage_edge_count")
    @classmethod
    def non_negative(cls, v: int) -> int:
        return max(0, v)
