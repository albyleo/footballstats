"""Download season CSVs from football-data.co.uk into data/raw/.

Free, no API key. Be polite: one file at a time with a short delay.

URL shape: https://football-data.co.uk/mmz4281/<SSSS>/<DIV>.csv
where SSSS is the season as start+end year, e.g. 2526 for 2025/26.

The www. host often returns nginx 503 while the apex host still serves the
same files. This script tries apex first, then www, with retries.

Examples:
    python scripts/fetch_football_data.py --seasons 2627 2526 --leagues E0
    python scripts/fetch_football_data.py --seasons 2425 --leagues E0 --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.error
import urllib.request

# Apex first: www.football-data.co.uk has been serving 503 while this works.
HOSTS = (
    "https://football-data.co.uk/mmz4281",
    "https://www.football-data.co.uk/mmz4281",
)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data", "raw")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


def season_label(s: str) -> str:
    """'2425' -> '2024-25', for readable filenames."""
    if len(s) == 4 and s.isdigit():
        return f"20{s[:2]}-{s[2:]}"
    return s


def _looks_like_csv(body: bytes) -> bool:
    head = body.lstrip().lstrip(b"\xef\xbb\xbf")
    return b"Div," in head[:400]


def _get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept": "text/csv,text/plain,*/*"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch(
    season: str, div: str, out_dir: str, dry_run: bool, force: bool,
    retries: int, delay: float,
) -> tuple[str, int]:
    dest = os.path.join(out_dir, f"{div}_{season_label(season)}.csv")
    if os.path.exists(dest) and not force:
        return ("exists", os.path.getsize(dest))
    urls = [f"{base}/{season}/{div}.csv" for base in HOSTS]
    if dry_run:
        return (f"would fetch {urls[0]}", 0)

    last_err = "no host tried"
    attempts = max(1, retries)
    for attempt in range(attempts):
        for url in urls:
            try:
                body = _get(url)
            except urllib.error.HTTPError as e:
                last_err = f"HTTP {e.code}"
                continue
            except Exception as e:
                last_err = f"error: {type(e).__name__}"
                continue
            if not _looks_like_csv(body):
                last_err = "not a football-data CSV (season not started?)"
                continue
            with open(dest, "wb") as fh:
                fh.write(body)
            return ("ok", len(body))
        if attempt + 1 < attempts:
            time.sleep(delay * (attempt + 1))
    return (last_err, 0)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--seasons", nargs="+", required=True,
                    help="season codes, e.g. 2627 2526")
    ap.add_argument("--leagues", nargs="+", required=True,
                    help="division codes, e.g. E0 SP1 I1 D1 F1")
    ap.add_argument("--out", default=OUT_DIR)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the URLs without downloading")
    ap.add_argument("--force", action="store_true",
                    help="re-download files that already exist")
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--retries", type=int, default=3,
                    help="attempts per file across hosts (default 3)")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    total = ok = 0
    for season in args.seasons:
        for div in args.leagues:
            status, size = fetch(
                season, div, args.out, args.dry_run, args.force,
                args.retries, args.delay,
            )
            kb = f"{size / 1024:.0f} KB" if size else ""
            print(f"  {div} {season_label(season)}: {status} {kb}")
            total += 1
            if status == "ok":
                ok += 1
                time.sleep(args.delay)

    print(f"\n{ok}/{total} downloaded into {args.out}")
    if ok:
        print("Next: python src/ingest.py --no-samples")
        return 0
    return 1 if not args.dry_run else 0


if __name__ == "__main__":
    raise SystemExit(main())
