"""Optional local MCP data-access layer: sandbox, guard and structured results.

The dashboard reads saved JSON/CSV independently and does not import this module.
All SQL exposed by the MCP server must go through this read-only connection.

Safety posture -- the connection is opened read-only *and* with external access
disabled, which is what actually stops a generated query from doing damage:

    write/DDL           -> InvalidInputException  (read_only)
    COPY ... TO 'file'  -> PermissionException    (no external access) <- exfiltration
    read_csv('C:/...')  -> PermissionException                         <- local file read
    ATTACH other.duckdb -> PermissionException

The textual check in check_readonly() exists for clearer error messages. The
engine is the enforcement boundary.
"""

from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass, field

import duckdb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("FOOTBALL_DB", os.path.join(ROOT, "football_mvp.duckdb"))

DEFAULT_MAX_ROWS = 100
HARD_MAX_ROWS = 1000

READ_PREFIXES = (
    "select", "with", "describe", "summarize", "explain", "show", "table",
    "values", "pivot", "from",
)

_BANNED = re.compile(
    r"\b(attach|copy|install|load|export|import|create|insert|update|delete|"
    r"drop|alter|set|reset|pragma|call)\b",
    re.I,
)


class QueryRejected(Exception):
    """The guard refused the SQL before it reached the engine."""


_root: duckdb.DuckDBPyConnection | None = None
_lock = threading.Lock()


def _root_connection() -> duckdb.DuckDBPyConnection:
    global _root
    with _lock:
        if _root is None:
            if not os.path.exists(DB_PATH):
                raise FileNotFoundError(
                    f"No database at {DB_PATH}. Run: python src/ingest.py"
                )
            _root = duckdb.connect(
                DB_PATH, read_only=True, config={"enable_external_access": False}
            )
        return _root


def cursor() -> duckdb.DuckDBPyConnection:
    """A per-call cursor over the shared read-only database.

    The web app serves requests from a thread pool and a single DuckDB
    connection object must not be used concurrently, so every call gets its own
    cursor. Cursors inherit the parent's read_only and no-external-access
    settings, so the sandbox still applies.
    """
    return _root_connection().cursor()


def _strip_sql_noise(sql: str) -> str:
    """Blank out comments and string literals so keyword checks aren't fooled
    by a team called 'Drop Table United' or by a `-- delete` comment."""
    s = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    s = re.sub(r"--[^\n]*", " ", s)
    s = re.sub(r"'(?:''|[^'])*'", "''", s)
    s = re.sub(r'"(?:""|[^"])*"', '""', s)
    return s


def check_readonly(sql: str) -> str | None:
    """Return a human-readable reason to refuse, or None to allow."""
    bare = _strip_sql_noise(sql).strip()
    if not bare:
        return "Empty query."
    if ";" in bare.rstrip().rstrip(";"):
        return "One statement per call, please."
    first = re.match(r"[a-zA-Z]+", bare)
    if not first or first.group(0).lower() not in READ_PREFIXES:
        got = first.group(0) if first else "?"
        return f"Only read queries are allowed (got '{got}'). Start with SELECT or WITH."
    banned = _BANNED.search(bare)
    if banned:
        return f"'{banned.group(1).upper()}' is not permitted."
    return None


@dataclass
class QueryResult:
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    total: int = 0
    cap: int = DEFAULT_MAX_ROWS

    @property
    def truncated(self) -> bool:
        return self.total > len(self.rows)


def run_query(sql: str, max_rows: int = DEFAULT_MAX_ROWS) -> QueryResult:
    """Execute guarded read-only SQL. Raises QueryRejected or a duckdb error."""
    problem = check_readonly(sql)
    if problem:
        raise QueryRejected(problem)
    cap = max(1, min(int(max_rows), HARD_MAX_ROWS))
    clean = sql.rstrip().rstrip(";")
    cur = cursor()
    rel = cur.sql(clean)
    cols = list(rel.columns)
    # Fetch one extra row to detect truncation without counting twice.
    rows = rel.fetchmany(cap + 1)
    total = len(rows)
    if total > cap:
        rows = rows[:cap]
        try:
            total = cursor().sql(f"SELECT count(*) FROM ({clean})").fetchone()[0]
        except Exception:
            total = cap + 1
    return QueryResult(columns=cols, rows=rows, total=total, cap=cap)


def find_team(name: str, limit: int = 10) -> tuple[list[str], list[tuple], bool]:
    """Resolve a team name. Returns (columns, rows, used_fuzzy_fallback)."""
    limit = max(1, min(int(limit), 50))
    cur = cursor()
    rows = cur.execute(
        """SELECT team, count(*) AS matches, min(date) AS first, max(date) AS last,
                  count(DISTINCT league_code) AS leagues
           FROM team_match_stats WHERE team ILIKE '%' || ? || '%'
           GROUP BY team ORDER BY matches DESC LIMIT ?""",
        [name, limit],
    ).fetchall()
    if rows:
        return ["team", "matches", "first", "last", "leagues"], rows, False
    # No substring hit: rank by similarity rather than reporting "not found",
    # which an LLM reads as "this team has no data".
    rows = cursor().execute(
        """SELECT team, count(*) AS matches,
                  round(max(jaro_winkler_similarity(lower(team), lower(?))), 3) AS similarity
           FROM team_match_stats GROUP BY team
           HAVING similarity > 0.6 ORDER BY similarity DESC LIMIT ?""",
        [name, limit],
    ).fetchall()
    return ["team", "matches", "similarity"], rows, True


def schema_objects() -> list[dict]:
    """Tables and views in main, with row counts and columns."""
    cur = cursor()
    out: list[dict] = []
    objs = cur.execute(
        "SELECT table_name, table_type FROM information_schema.tables "
        "WHERE table_schema='main' ORDER BY table_type DESC, table_name"
    ).fetchall()
    for name, kind in objs:
        try:
            n = cursor().execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]
        except Exception:
            n = None
        cols = cursor().execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema='main' AND table_name=? ORDER BY ordinal_position",
            [name],
        ).fetchall()
        out.append({
            "name": name,
            "kind": kind.lower(),
            "rows": n,
            "columns": [{"name": c, "type": t} for c, t in cols],
        })
    return out


def provenance() -> dict:
    """What is actually loaded -- including whether it is the synthetic fixture.

    The UI and the docs both need this: a chart built on invented numbers must
    say so on its face.
    """
    cur = cursor()
    try:
        files = [r[0] for r in cur.execute(
            "SELECT DISTINCT source_file FROM matches WHERE source_file IS NOT NULL "
            "ORDER BY 1").fetchall()]
        stats = cursor().execute(
            "SELECT count(*), min(date), max(date), count(DISTINCT league_code), "
            "count(DISTINCT season) FROM matches").fetchone()
    except Exception:
        return {"sources": [], "synthetic": False, "matches": 0, "error": "no match data"}
    return {
        "sources": files,
        "synthetic": any("SYNTHETIC" in f.upper() for f in files),
        "matches": stats[0],
        "date_from": str(stats[1]) if stats[1] else None,
        "date_to": str(stats[2]) if stats[2] else None,
        "leagues": stats[3],
        "seasons": stats[4],
        "db_path": DB_PATH,
    }
