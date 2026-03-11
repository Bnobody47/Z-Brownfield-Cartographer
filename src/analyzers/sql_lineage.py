from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Tuple

import sqlglot
from sqlglot import exp


@dataclass
class SqlStatementLineage:
    statement_index: int
    sources: set[str]
    targets: set[str]
    statement_sql: str
    line_range: Tuple[int, int] | None = None


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
        cleaned = self._preprocess_sql(raw)
        stmts = sqlglot.parse(cleaned, read=self.dialect)
        out: list[SqlStatementLineage] = []
        # simple line splitting used to approximate per-statement line ranges
        lines = cleaned.splitlines()
        for i, stmt in enumerate(stmts):
            sources = {self._normalize_table(t) for t in self._find_source_tables(stmt)}
            targets = {self._normalize_table(t) for t in self._find_target_tables(stmt)}
            # best-effort line range: find the first line containing the first few characters of the statement
            stmt_sql = stmt.sql(dialect=self.dialect) if hasattr(stmt, "sql") else str(stmt)
            snippet = stmt_sql.strip().splitlines()[0][:40]
            start_line = 1
            for idx, line in enumerate(lines, start=1):
                if snippet and snippet in line:
                    start_line = idx
                    break
            end_line = max(start_line, start_line + max(0, stmt_sql.count("\n")))
            out.append(
                SqlStatementLineage(
                    statement_index=i,
                    sources={s for s in sources if s},
                    targets={t for t in targets if t},
                    statement_sql=stmt_sql,
                    line_range=(start_line, end_line),
                )
            )
        return out

    _re_jinja_stmt = re.compile(r"\{%-?[\s\S]*?-?%\}", re.MULTILINE)
    _re_jinja_expr = re.compile(r"\{\{[\s\S]*?\}\}", re.MULTILINE)
    _re_ref = re.compile(r"\{\{\s*ref\(\s*'([^']+)'\s*\)\s*\}\}", re.IGNORECASE)
    _re_ref2 = re.compile(r'\{\{\s*ref\(\s*"([^"]+)"\s*\)\s*\}\}', re.IGNORECASE)
    _re_source = re.compile(
        r"\{\{\s*source\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)\s*\}\}",
        re.IGNORECASE,
    )
    _re_source2 = re.compile(
        r'\{\{\s*source\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)\s*\}\}',
        re.IGNORECASE,
    )

    def _preprocess_sql(self, sql: str) -> str:
        """
        Best-effort sanitizer for templated SQL (dbt/Jinja).

        Goals:
        - replace `{{ ref('model') }}` with `model`
        - replace `{{ source('schema','table') }}` with `schema.table`
        - strip `{% ... %}` blocks
        - strip any remaining `{{ ... }}` blocks to keep sqlglot parsing
        """
        s = sql
        s = self._re_jinja_stmt.sub(" ", s)
        s = self._re_source.sub(r"\1.\2", s)
        s = self._re_source2.sub(r"\1.\2", s)
        s = self._re_ref.sub(r"\1", s)
        s = self._re_ref2.sub(r"\1", s)
        s = self._re_jinja_expr.sub(" ", s)
        return s

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

