from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


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
