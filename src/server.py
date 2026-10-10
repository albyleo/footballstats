"""MCP server exposing the football DuckDB to an LLM.

Note on the SDK: the `mcp` Python package is 2.x, where FastMCP was renamed to
MCPServer. `from mcp.server.fastmcp import FastMCP` raises ModuleNotFoundError
on this version.

MCP data access and the read-only sandbox live in src/db.py. The dashboard
does not use this optional local server or its separate DuckDB database.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db  # noqa: E402
from mcp.server.mcpserver import MCPServer  # noqa: E402

MAX_CHARS = 20_000

INSTRUCTIONS = """Football statistics database (DuckDB, read-only SQL).

Start with describe_schema() -- the raw CSV columns are cryptic and one of them
("AS" = away shots) is a SQL keyword.

Two rules that prevent most wrong answers:
1. For "which team had the most X", query team_match_stats or team_match_form
   (one row per team per match). Grouping the wide `matches` view by home_team
   answers "most X at home", which is a different and usually wrong question.
2. Team names are abbreviated ("Man United", "Nott'm Forest", "Wolves"). Resolve
   a name with find_team() before filtering on it, or you will silently get zero
   rows.
"""

mcp = MCPServer(name="FootballAnalytics", instructions=INSTRUCTIONS, version="0.1.0")


def _cell(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)


def _as_table(cols: list[str], rows: list[tuple], total: int, capped: int) -> str:
    if not rows:
        return (
            "0 rows.\n\nIf you filtered on a team name, check it with "
            "find_team() -- names are abbreviated in this dataset."
        )
    body = [" | ".join(cols), " | ".join("---" for _ in cols)]
    body += [" | ".join(_cell(v) for v in r) for r in rows]
    out = "\n".join(body)
    if len(out) > MAX_CHARS:
        keep, acc = [], 0
        for line in body:
            if acc + len(line) > MAX_CHARS:
                break
            keep.append(line)
            acc += len(line) + 1
        out = "\n".join(keep) + f"\n... output truncated at {MAX_CHARS} chars"
    if total > capped:
        out += f"\n\n({capped} of {total} rows shown -- add LIMIT or aggregate.)"
    else:
        out += f"\n\n({total} row{'s' if total != 1 else ''})"
    return out


@mcp.tool()
def describe_schema() -> str:
    """Tables, columns and column meanings for the football database.

    Call this before writing SQL: the underlying CSV columns are abbreviated.
    """
    parts: list[str] = []
    for obj in db.schema_objects():
        n = obj["rows"] if obj["rows"] is not None else "?"
        parts.append(f"\n## {obj['name']}  ({obj['kind']}, {n} rows)")
        parts.append(", ".join(f"{c['name']} {c['type']}" for c in obj["columns"]))

    prov = db.provenance()
    warning = ""
    if prov.get("synthetic"):
        warning = (
            "\n!! This database currently contains SYNTHETIC FIXTURE data "
            "(invented results used to test the pipeline). Do not present these "
            "numbers as real. Sources: " + ", ".join(prov["sources"]) + "\n"
        )

    return (
        "# Football database\n"
        + warning
        + "\n".join(parts)
        + """

# Which object to query

- team_match_form -- START HERE. One row per (match, team), plus outcome,
  points, and games_ago_overall / games_ago_in_season (1 = most recent).
  "Last 20 games" is `WHERE games_ago_overall <= 20`.
- team_match_stats -- same long shape, without the form columns.
- matches -- one row per match, typed, home_/away_ prefixed. Use only when the
  home/away distinction is the point of the question.
- raw_matches -- untouched CSV, all VARCHAR. Includes betting odds columns.
  Column "AS" (away shots) is a SQL keyword: write "AS" quoted.
- player_season_stats -- per-player season aggregates, if a players file was
  ingested. Season totals, not per-match.

# Column meanings (per-team, in the long views)

goals_for/goals_against, ht_goals_for/against (half-time), shots,
shots_on_target, corners, fouls_committed, yellows, reds.
Defensive mirrors: shots_faced, corners_faced, fouls_suffered.
is_home BOOLEAN, opponent, season ('2024/2025'), league_code ('E0'), date DATE.

Stats are NULL (not 0) for older seasons where the source CSV omits them --
prefer avg() over sum() when comparing across eras, and filter
`WHERE corners IS NOT NULL` when counting.

# Examples

-- Most corners overall, last 20 games each
SELECT team, sum(corners) AS c, count(*) AS games
FROM team_match_form
WHERE league_code='E0' AND games_ago_overall <= 20
GROUP BY team ORDER BY c DESC;

-- Most fouls per game this season
SELECT team, round(avg(fouls_committed), 2) AS fouls_pg
FROM team_match_form
WHERE season='2024/2025' AND fouls_committed IS NOT NULL
GROUP BY team ORDER BY fouls_pg DESC;

-- Home vs away split for one team
SELECT is_home, avg(goals_for) gf, avg(goals_against) ga
FROM team_match_form WHERE team='Arsenal' GROUP BY is_home;
"""
    )


@mcp.tool()
def find_team(name: str, limit: int = 10) -> str:
    """Resolve a team name to the exact spelling used in the database.

    Use this before filtering on a team. 'Manchester United' is stored as
    'Man United' and would otherwise match nothing.
    """
    cols, rows, fuzzy = db.find_team(name, limit)
    if not rows:
        return f"No team matching {name!r}. Try SELECT DISTINCT team FROM team_match_stats."
    table = _as_table(cols, rows, len(rows), len(rows))
    if fuzzy:
        return "No exact substring match. Closest names:\n\n" + table
    return table


@mcp.tool()
def query(sql: str, max_rows: int = db.DEFAULT_MAX_ROWS) -> str:
    """Run a read-only SQL query against the football database.

    DuckDB dialect. Returns a markdown table. Prefer team_match_form for
    per-team questions; see describe_schema() for columns and examples.
    """
    try:
        r = db.run_query(sql, max_rows)
    except db.QueryRejected as e:
        return f"Query rejected: {e}"
    except Exception as e:
        return f"SQL error: {type(e).__name__}: {e}"
    return _as_table(r.columns, r.rows, r.total, r.cap)


if __name__ == "__main__":
    if not os.path.exists(db.DB_PATH):
        print(f"No database at {db.DB_PATH}\nRun: python src/ingest.py", file=sys.stderr)
        raise SystemExit(1)
    mcp.run(transport="stdio")
