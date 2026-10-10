"""Canonical schema for the football analytics MVP.

Two ideas carry this module:

1. The raw football-data.co.uk CSVs are stored verbatim (all VARCHAR) so no
   ingest-time type inference can silently mangle them.
2. Everything downstream reads *views* that are typed, normalised and
   long-format. The views are where the domain knowledge lives.
"""

from __future__ import annotations

# --- date parsing -----------------------------------------------------------
# football-data.co.uk uses dd/mm/yyyy in recent seasons and dd/mm/yy in older
# ones. try_strptime('17/08/24', '%d/%m/%Y') happily returns year 24 AD, which
# makes every `WHERE date >= '2024-08-01'` filter silently return nothing. So we
# expand two-digit years first: >=90 -> 19xx (the archive starts in 1993),
# otherwise 20xx.
def date_expr(col: str) -> str:
    return rf"""try_strptime(
        regexp_replace(
          regexp_replace(nullif(trim({col}), ''),
            '^(\d{{1,2}})/(\d{{1,2}})/(9\d)$', '\1/\2/19\3'),
            '^(\d{{1,2}})/(\d{{1,2}})/(\d{{2}})$', '\1/\2/20\3'),
        '%d/%m/%Y')::DATE"""


# --- league codes -----------------------------------------------------------
LEAGUES = {
    "E0": ("England", "Premier League", 1),
    "E1": ("England", "Championship", 2),
    "E2": ("England", "League One", 3),
    "E3": ("England", "League Two", 4),
    "EC": ("England", "National League", 5),
    "SC0": ("Scotland", "Premiership", 1),
    "SC1": ("Scotland", "Championship", 2),
    "D1": ("Germany", "Bundesliga", 1),
    "D2": ("Germany", "2. Bundesliga", 2),
    "SP1": ("Spain", "La Liga", 1),
    "SP2": ("Spain", "Segunda Division", 2),
    "I1": ("Italy", "Serie A", 1),
    "I2": ("Italy", "Serie B", 2),
    "F1": ("France", "Ligue 1", 1),
    "F2": ("France", "Ligue 2", 2),
    "N1": ("Netherlands", "Eredivisie", 1),
    "B1": ("Belgium", "Pro League", 1),
    "P1": ("Portugal", "Primeira Liga", 1),
    "T1": ("Turkey", "Super Lig", 1),
    "G1": ("Greece", "Super League", 1),
}

# --- raw -> canonical column mapping ---------------------------------------
# Left: our name. Right: the football-data.co.uk column, which is terse and, in
# the case of "AS" (away shots), an actual SQL keyword that must stay quoted --
# `SELECT AS FROM t` is a parser error.
MATCH_INT_COLS = {
    "home_goals": "FTHG",
    "away_goals": "FTAG",
    "home_ht_goals": "HTHG",
    "away_ht_goals": "HTAG",
    "home_shots": "HS",
    "away_shots": "AS",
    "home_shots_on_target": "HST",
    "away_shots_on_target": "AST",
    "home_corners": "HC",
    "away_corners": "AC",
    "home_fouls": "HF",
    "away_fouls": "AF",
    "home_yellows": "HY",
    "away_yellows": "AY",
    "home_reds": "HR",
    "away_reds": "AR",
}

# Per-team stat columns for the long view, as (canonical, home_src, away_src).
# "faced"/"suffered" columns are the opponent's value from that team's
# perspective, which is what defensive questions actually need.
TEAM_STATS = [
    ("goals_for", "home_goals", "away_goals"),
    ("goals_against", "away_goals", "home_goals"),
    ("ht_goals_for", "home_ht_goals", "away_ht_goals"),
    ("ht_goals_against", "away_ht_goals", "home_ht_goals"),
    ("shots", "home_shots", "away_shots"),
    ("shots_on_target", "home_shots_on_target", "away_shots_on_target"),
    ("corners", "home_corners", "away_corners"),
    ("fouls_committed", "home_fouls", "away_fouls"),
    ("yellows", "home_yellows", "away_yellows"),
    ("reds", "home_reds", "away_reds"),
    ("shots_faced", "away_shots", "home_shots"),
    ("corners_faced", "away_corners", "home_corners"),
    ("fouls_suffered", "away_fouls", "home_fouls"),
]

# Season runs Aug->May, so a match before July belongs to the season that
# started the previous calendar year.
_SEASON_START = (
    "CASE WHEN t.date IS NULL THEN NULL "
    "WHEN month(t.date) >= 7 THEN year(t.date) ELSE year(t.date) - 1 END"
)


def matches_view_sql(available: set[str]) -> str:
    """Typed, one-row-per-match view over raw_matches.

    `available` is the set of columns actually present in raw_matches; older
    seasons and lower divisions omit the shot/corner/foul block entirely, so
    missing columns are projected as typed NULLs rather than blowing up the DDL.
    """
    stat_exprs = []
    for canon, raw in MATCH_INT_COLS.items():
        if raw in available:
            stat_exprs.append(
                f"""TRY_CAST(NULLIF(TRIM("{raw}"), '') AS INT) AS {canon}"""
            )
        else:
            stat_exprs.append(f"CAST(NULL AS INT) AS {canon}")
    stats_block = ",\n        ".join(stat_exprs)

    def opt(col: str, alias: str) -> str:
        if col in available:
            return f"""NULLIF(TRIM("{col}"), '') AS {alias}"""
        return f"CAST(NULL AS VARCHAR) AS {alias}"

    # Explicit projection, not `t.* EXCLUDE (...)`: the leagues join also
    # supplies country/league_name, and a star would emit them twice.
    stat_out = ",\n      ".join(f"t.{c}" for c in MATCH_INT_COLS)

    return f"""
    CREATE OR REPLACE VIEW matches AS
    WITH typed AS (
      SELECT
        match_id,
        source_file,
        TRIM("Div") AS league_code,
        {date_expr('"Date"')} AS date,
        {opt('Time', 'kickoff_time')},
        TRIM("HomeTeam") AS home_team,
        TRIM("AwayTeam") AS away_team,
        {opt('Referee', 'referee')},
        {stats_block}
      FROM raw_matches
    )
    SELECT
      t.match_id,
      t.date,
      {_SEASON_START} AS season_start_year,
      CASE WHEN t.date IS NULL THEN NULL
           ELSE ({_SEASON_START})::VARCHAR || '/' || (({_SEASON_START}) + 1)::VARCHAR
      END AS season,
      t.league_code,
      l.country,
      l.league_name,
      t.kickoff_time,
      t.home_team,
      t.away_team,
      t.referee,
      {stat_out},
      CASE WHEN t.home_goals > t.away_goals THEN 'H'
           WHEN t.home_goals < t.away_goals THEN 'A'
           WHEN t.home_goals IS NOT NULL THEN 'D' END AS result,
      t.source_file
    FROM typed t
    LEFT JOIN leagues l ON l.league_code = t.league_code
    """


def team_match_stats_view_sql() -> str:
    """One row per (match, team) -- the view almost every question should use.

    The wide home/away layout invites a specific, silent bug: grouping by
    HomeTeam and summing HC answers "most corners *at home*", not "most
    corners". Unioning the two perspectives makes the correct query the
    obvious one.
    """
    shared = """match_id, date, season, season_start_year, league_code, country,
        league_name, kickoff_time, referee"""
    home = ",\n        ".join(f"{src} AS {canon}" for canon, src, _ in TEAM_STATS)
    away = ",\n        ".join(f"{src} AS {canon}" for canon, _, src in TEAM_STATS)
    return f"""
    CREATE OR REPLACE VIEW team_match_stats AS
    SELECT
        {shared},
        home_team AS team, away_team AS opponent, TRUE AS is_home,
        {home},
        source_file
    FROM matches
    UNION ALL
    SELECT
        {shared},
        away_team AS team, home_team AS opponent, FALSE AS is_home,
        {away},
        source_file
    FROM matches
    """


TEAM_FORM_VIEW_SQL = """
CREATE OR REPLACE VIEW team_match_form AS
SELECT
    *,
    CASE WHEN goals_for > goals_against THEN 'W'
         WHEN goals_for < goals_against THEN 'L'
         WHEN goals_for IS NOT NULL THEN 'D' END AS outcome,
    CASE WHEN goals_for > goals_against THEN 3
         WHEN goals_for < goals_against THEN 0
         WHEN goals_for IS NOT NULL THEN 1 END AS points,
    -- Reverse-chronological index per team: 1 = most recent match. Turns
    -- "last N games" into a plain filter instead of a correlated subquery,
    -- which is the query an LLM most often gets wrong.
    row_number() OVER (
        PARTITION BY team, season ORDER BY date DESC, match_id DESC
    ) AS games_ago_in_season,
    row_number() OVER (
        PARTITION BY team ORDER BY date DESC, match_id DESC
    ) AS games_ago_overall
FROM team_match_stats
WHERE date IS NOT NULL
"""


def leagues_table_sql() -> str:
    rows = ",\n        ".join(
        f"('{code}', '{country}', '{name.replace(chr(39), chr(39) * 2)}', {tier})"
        for code, (country, name, tier) in LEAGUES.items()
    )
    return f"""
    CREATE OR REPLACE TABLE leagues (
        league_code VARCHAR, country VARCHAR, league_name VARCHAR, tier INT
    );
    INSERT INTO leagues VALUES
        {rows};
    """
