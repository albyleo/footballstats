"""Bounded provider downloads; credentials never enter output or saved JSON."""
from __future__ import annotations

import argparse
import hashlib
import time
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CONFIG = {
    "api-football": ("https://v3.football.api-sports.io", "API_FOOTBALL_KEY", "x-apisports-key"),
    "sportmonks": ("https://api.sportmonks.com/v3/football", "SPORTMONKS_TOKEN", "Authorization"),
}


def load_env():
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            name, sep, value = line.partition("=")
            if sep and name.strip() in {c[1] for c in CONFIG.values()} | {'FOOTBALL_DATA_ORG'}:
                os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


class Client:
    def __init__(self, provider, budget=10):
        load_env()
        self.provider = provider
        self.base, variable, self.header = CONFIG[provider]
        self.key = os.environ.get(variable, "").strip()
        if not self.key:
            raise ValueError(f"Missing {variable}: fill {ROOT / '.env'}")
        self.remaining = budget
        self.network_requests = 0
        self.cache_hits = 0
        self.last_fetched_at = None

    def get(self, endpoint, **params):
        fingerprint = hashlib.sha256((self.key + endpoint + json.dumps(params, sort_keys=True)).encode()).hexdigest()
        cache = ROOT / "data" / "providers" / self.provider / "cache" / f"{fingerprint}.json"
        if cache.exists() and time.time() - cache.stat().st_mtime < 86400:
            self.cache_hits += 1
            self.last_fetched_at = datetime.fromtimestamp(cache.stat().st_mtime, timezone.utc).isoformat()
            return json.loads(cache.read_text(encoding="utf-8"))
        if self.remaining <= 0:
            raise ValueError("Request budget exhausted; narrow the selection or raise --max-requests.")
        self.remaining -= 1
        self.network_requests += 1
        request = Request(self.base + endpoint + "?" + urlencode(params), headers={
            self.header: self.key, "Accept": "application/json", "User-Agent": "FootballMVP/1.0"})
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.load(response)
        except HTTPError as exc:
            raise ValueError(f"{self.provider}: HTTP {exc.code}; check credentials, subscription and quota.") from None
        except (URLError, TimeoutError, OSError):
            raise ValueError(f"{self.provider}: connection failed (timeout/network).") from None
        except ValueError:
            raise ValueError(f"{self.provider}: invalid JSON response.") from None
        if not isinstance(payload, dict):
            raise ValueError("Unexpected provider response.")
        if payload.get("errors") or payload.get("error") or (
            self.provider == "sportmonks" and "data" not in payload
        ):
            # Do not echo arbitrary error bodies: they may contain credentials.
            detail = json.dumps(payload.get("errors") or payload.get("error") or payload.get("message"))
            detail = detail.replace(self.key, "[REDACTED]")[:400]
            raise ValueError(f"{self.provider}: API refused request: {detail}")
        # Avoid caching account details or token-bearing pagination URLs.
        if endpoint != "/status":
            clean = dict(payload)
            if "pagination" in clean:
                clean["pagination"] = {k: v for k, v in clean["pagination"].items() if k != "next_page"}
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(clean).replace(self.key, "[REDACTED]"), encoding="utf-8")
        self.last_fetched_at = datetime.now(timezone.utc).isoformat()
        return payload

    def save(self, label, payload, quiet=False):
        directory = ROOT / "data" / "providers" / self.provider
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{label}.json"
        # Only retain data fields; pagination URLs may carry authentication tokens.
        clean = {"provider": self.provider, "fetched_at": self.last_fetched_at or datetime.now(timezone.utc).isoformat(),
                 "data": payload.get("response", payload.get("data")),
                 "pagination": {k: v for k, v in payload.get("pagination", {}).items()
                                if k in ("current_page", "has_more", "per_page")}}
        serialized = json.dumps(clean, ensure_ascii=False, indent=2)
        serialized = serialized.replace(self.key, "[REDACTED]")
        temporary = path.with_suffix(".tmp")
        temporary.write_text(serialized, encoding="utf-8")
        temporary.replace(path)
        if not quiet:
            print(f"Saved {path}")


def sync_sportmonks(client, start, end, league=None):
    """Fetch up to 50 complete fixture payloads per call, with bounded pagination."""
    first = datetime.strptime(start, "%Y-%m-%d")
    last = datetime.strptime(end, "%Y-%m-%d")
    if not 0 <= (last - first).days < 100:
        raise ValueError("Choose a date range of 1 to 100 days.")
    page, count, complete = 1, 0, False
    ids = set()
    filters = f"fixtureLeagues:{league or '271,501'};fixtureStates:5"
    includes = "participants;scores;state;season;league;statistics.type;lineups.details.type;events.type;periods"
    directory = ROOT / "data/providers/sportmonks"
    directory.mkdir(parents=True, exist_ok=True)
    summary = {"start": start, "end": end, "league_ids": [league] if league else [271, 501]}
    try:
        while True:
            payload = client.get(f"/fixtures/between/{start}/{end}", page=page, per_page=50,
                                 filters=filters, include=includes, order="asc")
            matches = payload.get("data")
            if not isinstance(matches, list):
                raise ValueError("Unexpected fixture list from Sportmonks.")
            for match in matches:
                if (match.get("state") or {}).get("state") != "FT":
                    continue
                if match["id"] in ids:
                    raise ValueError("Provider repeated a fixture across pages; stopping pagination.")
                ids.add(match["id"])
                client.save(f"match-{match['id']}", {"data": match}, quiet=True)
                count += 1
            print(f"Page {page}: {len(matches)} fixtures; {count} completed saved.", flush=True)
            if not payload.get("pagination", {}).get("has_more"):
                complete = True
                break
            if not matches:
                raise ValueError("Empty page with has_more=true; stopping pagination.")
            page += 1
    finally:
        summary.update(complete=complete, fixtures=count, network_requests=client.network_requests,
                       cache_hits=client.cache_hits, updated_at=datetime.now(timezone.utc).isoformat())
        path = directory / "sync-status.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        temporary.replace(path)
        print(f"Network requests: {client.network_requests}; cache hits: {client.cache_hits}; complete: {complete}")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=CONFIG)
    parser.add_argument("action", choices=["check", "leagues", "fixtures", "match", "sync"])
    parser.add_argument("--from-date", help="Sportmonks sync start date YYYY-MM-DD")
    parser.add_argument("--to-date", help="Sportmonks sync end date YYYY-MM-DD")
    parser.add_argument("--league", type=int)
    parser.add_argument("--season", type=int, help="API-Football season start year")
    parser.add_argument("--date", help="Sportmonks fixture date YYYY-MM-DD")
    parser.add_argument("--fixture", type=int)
    parser.add_argument("--max-requests", type=int, default=10)
    args = parser.parse_args()
    if args.max_requests < 1:
        parser.error("--max-requests must be positive")
    try:
        c = Client(args.provider, args.max_requests)
        af = args.provider == "api-football"
        if args.action == "sync":
            if af or not args.from_date or not args.to_date:
                parser.error("sync requires sportmonks --from-date YYYY-MM-DD --to-date YYYY-MM-DD")
            sync_sportmonks(c, args.from_date, args.to_date, args.league)
        elif args.action == "check":
            payload = c.get("/status" if af else "/leagues", **({} if af else {"per_page": 1}))
            print("Authentication/request OK. This does not confirm current-season statistics access.")
            if af:
                response = payload.get("response", {})
                print(json.dumps({k: response.get(k) for k in ("subscription", "requests")}, indent=2))
        elif args.action == "leagues":
            params = {"id": args.league} if af and args.league else {}
            if af and args.season:
                params["season"] = args.season
            if af:
                c.save("leagues", c.get("/leagues", **params))
            else:
                page = 1
                while True:
                    payload = c.get("/leagues", page=page, per_page=50, include="currentSeason")
                    c.save(f"leagues-page-{page}", payload)
                    if not payload.get("pagination", {}).get("has_more"):
                        break
                    page += 1
        elif args.action == "fixtures":
            if af:
                if not args.league or not args.season:
                    parser.error("API-Football fixtures require --league and --season")
                c.save(f"fixtures-{args.league}-{args.season}", c.get("/fixtures", league=args.league, season=args.season))
            else:
                if not args.date:
                    parser.error("Sportmonks fixtures require --date YYYY-MM-DD")
                datetime.strptime(args.date, "%Y-%m-%d")
                page = 1
                while True:
                    params = {"page": page, "per_page": 50, "include": "participants;scores;state"}
                    if args.league:
                        params["filters"] = f"fixtureLeagues:{args.league}"
                    payload = c.get(f"/fixtures/date/{args.date}", **params)
                    c.save(f"fixtures-{args.date}-{args.league or 'all'}-page-{page}", payload)
                    if not payload.get("pagination", {}).get("has_more"):
                        break
                    page += 1
        else:
            if not args.fixture:
                parser.error("match requires --fixture ID (provider-specific)")
            if af:
                if args.max_requests < 3:
                    parser.error("API-Football match requires a budget of at least 3")
                for endpoint, params, suffix in [
                    ("/fixtures", {"id": args.fixture}, "fixture"),
                    ("/fixtures/statistics", {"fixture": args.fixture}, "teams"),
                    ("/fixtures/players", {"fixture": args.fixture}, "players"),
                ]:
                    payload = c.get(endpoint, **params)
                    c.save(f"match-{args.fixture}-{suffix}", payload)
                    if not payload.get("response"):
                        print(f"No {suffix} data returned; do not interpret missing statistics as zero.")
            else:
                payload = c.get(f"/fixtures/{args.fixture}", include="participants;scores;state;statistics.type;lineups.details.type")
                c.save(f"match-{args.fixture}", payload)
                if not (payload.get("data") or {}).get("lineups"):
                    print("No player lineups/statistics returned for this fixture.")
        return 0
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
