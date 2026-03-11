from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import sqlglot
from sqlglot import exp


@dataclass
class SqlStatementLineage:
    statement_index: int
    sources: set[str]
    targets: set[str]
    statement_sql: str


def _stable_id(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()[:24]


class SQLLineageAnalyzer:
    def __init__(self, dialect: Optional[str] = None) -> None:
        self.dialect = dialect

    def analyze_file(self, path: Path) -> list[SqlStatementLineage]:
        raw = path.read_text(encoding="utf-8", errors="replace")
        stmts = sqlglot.parse(raw, read=self.dialect)
        out: list[SqlStatementLineage] = []
        for i, stmt in enumerate(stmts):
            sources = {self._normalize_table(t) for t in self._find_source_tables(stmt)}
            targets = {self._normalize_table(t) for t in self._find_target_tables(stmt)}
            out.append(
                SqlStatementLineage(
                    statement_index=i,
                    sources={s for s in sources if s},
                    targets={t for t in targets if t},
                    statement_sql=stmt.sql(dialect=self.dialect) if hasattr(stmt, "sql") else str(stmt),
                )
            )
        return out

    def _find_source_tables(self, stmt: exp.Expression) -> Iterable[str]:
        # Tables referenced anywhere; we'll subtract targets later in graph logic if needed
        for t in stmt.find_all(exp.Table):
            yield t.sql(dialect=self.dialect)

    def _find_target_tables(self, stmt: exp.Expression) -> Iterable[str]:
        # CREATE TABLE ... AS SELECT ..., INSERT INTO ..., MERGE INTO ...
        for create in stmt.find_all(exp.Create):
            if isinstance(create.this, exp.Table):
                yield create.this.sql(dialect=self.dialect)
        for insert in stmt.find_all(exp.Insert):
            if isinstance(insert.this, exp.Table):
                yield insert.this.sql(dialect=self.dialect)
        for merge in stmt.find_all(exp.Merge):
            if isinstance(merge.this, exp.Table):
                yield merge.this.sql(dialect=self.dialect)

    def _normalize_table(self, raw: str) -> str:
        return raw.strip().strip("`").strip('"')

    def transformation_id(self, rel_file: str, stmt: SqlStatementLineage) -> str:
        return _stable_id("sql", rel_file, str(stmt.statement_index), stmt.statement_sql[:2000])

