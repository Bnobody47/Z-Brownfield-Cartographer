from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ParsedConfig:
    path: str
    kind: str  # "dbt_schema" | "unknown"
    data: dict[str, Any]


class DAGConfigAnalyzer:
    """
    Interim: YAML parsing scaffold.
    Final version should understand dbt schema.yml, Airflow configs, Prefect flows, etc.
    """

    def analyze_yaml(self, path: Path) -> ParsedConfig | None:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
            if not isinstance(data, dict):
                return None
            kind = "dbt_schema" if "models" in data or "sources" in data else "unknown"
            return ParsedConfig(path=path.as_posix(), kind=kind, data=data)
        except Exception:
            return None

