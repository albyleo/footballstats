"""Build football_mvp.duckdb from whatever CSVs are sitting in data/.

Idempotent: re-run it any time, it rebuilds tables from scratch. Raw CSVs are
loaded as all-VARCHAR and typed later in views, so a malformed cell degrades to
NULL in one column instead of derailing type inference for a whole file.

Usage:
    python src/ingest.py                 # data/raw + data/samples
    python src/ingest.py --no-samples    # data/raw only (real data)
    python src/ingest.py --players PATH  # also load an API-Football export
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys

import duckdb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import schema  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "football_mvp.duckdb")

# football-data.co.uk match files must have these; anything else in data/raw is
# skipped with a warning rather than corrupting the table.
REQUIRED = {"Div", "Date", "HomeTeam", "AwayTeam"}

NUMERIC_PLAYER_PREFIXES = (
    "games_", "shots_", "goals_", "passes_", "tackles_", "duels_",
    "dribbles_", "fouls_", "cards_", "penalty_", "substitutes_",
)


def snake(name: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", name.strip()).strip("_").lower()
    return re.sub(r"_+", "_", s) or "col"


def csv_columns(con: duckdb.DuckDBPyConnection, path: str, delim: str = ",") -> list[str]:
    """Header of a single CSV, without reading the body."""
    rows = con.execute(
        "SELECT column_name FROM (DESCRIBE SELECT * FROM read_csv(?, "
        "delim=?, header=true, all_varchar=true, sample_size=1, encoding='utf-8'))",
        [path, delim],
    ).fetchall()
    return [r[0] for r in rows]


def load_matches(con: duckdb.DuckDBPyConnection, paths: list[str]) -> int:
    usable: list[str] = []
    for p in paths:
        try:
            cols = set(csv_columns(con, p))
        except Exception as e:
            print(f"  ! skip {os.path.basename(p)}: unreadable ({str(e)[:60]})")
            continue
        missing = REQUIRED - cols
        if missing:
            print(f"  ! skip {os.path.basename(p)}: missing {sorted(missing)}")
            continue
        usable.append(p)

    if not usable:
        con.execute(
            """CREATE OR REPLACE TABLE raw_matches AS
               SELECT NULL::VARCHAR AS match_id, NULL::VARCHAR AS source_file,
                      NULL::VARCHAR AS "Div", NULL::VARCHAR AS "Date",
                      NULL::VARCHAR AS "HomeTeam", NULL::VARCHAR AS "AwayTeam"
               WHERE FALSE"""
        )
        return 0

    # union_by_name lets seasons with different column sets coexist (missing
    # ones arrive as NULL); null_padding tolerates the ragged trailing commas
    # football-data.co.uk files are prone to.
    con.execute(
        f"""
        CREATE OR REPLACE TABLE raw_matches AS
        SELECT
            md5(coalesce("Div",'') || '|' || coalesce("Date",'') || '|' ||
                coalesce("HomeTeam",'') || '|' || coalesce("AwayTeam",'')) AS match_id,
            regexp_replace(filename, '^.*[/\\\\]', '') AS source_file,
            * EXCLUDE (filename)
        FROM read_csv({usable!r},
                      delim=',', header=true, all_varchar=true,
                      union_by_name=true, null_padding=true,
                      ignore_errors=true, filename=true, encoding='utf-8')
        WHERE nullif(trim("HomeTeam"), '') IS NOT NULL
        """
    )
    return con.execute("SELECT count(*) FROM raw_matches").fetchone()[0]


def load_players(con: duckdb.DuckDBPyConnection, path: str) -> int:
    """Load an API-Football 'players statistics' export (semicolon-delimited)."""
    # Sniff the delimiter: these exports are ';' but a re-save can turn them ','.
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        head = fh.readline()
    delim = ";" if head.count(";") > head.count(",") else ","

    cols = csv_columns(con, path, delim)
    seen: dict[str, int] = {}
    renames = []
    for c in cols:
        s = snake(c)
        if s in seen:
            seen[s] += 1
            s = f"{s}_{seen[s]}"
        else:
            seen[s] = 0
        renames.append(f'"{c}" AS {s}')

    con.execute(
        f"""CREATE OR REPLACE TABLE raw_player_season_stats AS
            SELECT {', '.join(renames)}
            FROM read_csv(?, delim=?, header=true, all_varchar=true,
                          null_padding=true, ignore_errors=true)""",
        [path, delim],
    )

    present = {r[0] for r in con.execute("DESCRIBE raw_player_season_stats").fetchall()}
    projected = []
    for c in sorted(present):
        if c.startswith(NUMERIC_PLAYER_PREFIXES) or c == "age":
            projected.append(f"TRY_CAST(NULLIF(TRIM({c}), '') AS DOUBLE) AS {c}")
        elif c in ("height", "weight"):
            # Stored as '177 cm' / '70 kg'.
            projected.append(
                f"TRY_CAST(regexp_extract({c}, '(\\d+)', 1) AS INT) AS {c}_num"
            )
        else:
            projected.append(f"NULLIF(TRIM({c}), '') AS {c}")

    con.execute(
        f"CREATE OR REPLACE VIEW player_season_stats AS "
        f"SELECT {', '.join(projected)} FROM raw_player_season_stats"
    )
    return con.execute("SELECT count(*) FROM raw_player_season_stats").fetchone()[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-samples", action="store_true",
                    help="ignore data/samples (synthetic fixtures)")
    ap.add_argument("--players", default=None,
                    help="path to an API-Football player statistics CSV")
    ap.add_argument("--db", default=DB_PATH)
    args = ap.parse_args()

    paths = sorted(glob.glob(os.path.join(ROOT, "data", "raw", "*.csv")))
    if not args.no_samples:
        paths += sorted(glob.glob(os.path.join(ROOT, "data", "samples", "*.csv")))

    if not paths:
        print(
            "No match CSVs found.\n"
            "  Fetch first, or drop --no-samples to load the synthetic fixture:\n"
            "    python scripts/fetch_football_data.py --seasons 2627 2526 "
            "--leagues E0 SP1 I1 D1 F1\n"
            "    python src/ingest.py\n"
            "Refusing to rebuild an empty database.",
            file=sys.stderr,
        )
        return 1

    con = duckdb.connect(args.db)
    con.execute("BEGIN")
    try:
        con.execute(schema.leagues_table_sql())

        print(f"Loading {len(paths)} match CSV(s)...")
        n_matches = load_matches(con, paths)

        available = {r[0] for r in con.execute("DESCRIBE raw_matches").fetchall()}
        con.execute(schema.matches_view_sql(available))
        con.execute(schema.team_match_stats_view_sql())
        con.execute(schema.TEAM_FORM_VIEW_SQL)

        n_players = 0
        if args.players:
            if os.path.exists(args.players):
                print(f"Loading players from {os.path.basename(args.players)}...")
                n_players = load_players(con, args.players)
            else:
                print(f"  ! players file not found: {args.players}")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise

    print(f"\n  matches           {n_matches:>7,} rows")
    if n_matches:
        rng = con.execute(
            "SELECT min(date), max(date), count(DISTINCT league_code), "
            "count(DISTINCT season) FROM matches"
        ).fetchone()
        print(f"  date range        {rng[0]} -> {rng[1]}")
        print(f"  leagues / seasons {rng[2]} / {rng[3]}")
        print(f"  team_match_stats  {con.execute('SELECT count(*) FROM team_match_stats').fetchone()[0]:>7,} rows")
    if n_players:
        print(f"  player rows       {n_players:>7,}")
    print(f"\nDatabase: {args.db}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
