"""Read-only dashboard over saved provider data. No downloads or database required.

Run: python src/webapp.py --port 8078
Feed acquisition is a separate CLI process in scripts/fetch_provider.py.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import provider_stats
import cloud_store
from report_cache import ReportCache
import uvicorn
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

STATIC = Path(__file__).resolve().parent / "static"
REPORT_CACHE = ReportCache()


async def provider_page(request):
    return FileResponse(STATIC / "providers.html", headers={"Cache-Control": "no-cache"})


async def provider_report(request):
    p = request.query_params
    try:
        if len(request.url.query) > 2048 or any(len(p.get(k, "")) > 128
                for k in ("league", "season", "team", "search")):
            raise ValueError("Filtri troppo lunghi")
        args = (p.get("kind", "players"), p.get("metric", "shots-on-target"),
                p.get("league", ""), p.get("season", ""), max(0, int(p.get("min_minutes", "0"))),
                p.get("team", ""), p.get("search", ""),
                max(0, min(100, int(p.get("last_n", "0")))), p.get("sort", "total"))

        def read_local():
            if cloud_store.enabled():
                snapshot = cloud_store.SNAPSHOTS.get()
                return REPORT_CACHE.get(args, ('supabase', snapshot['revision']),
                                        lambda: provider_stats.report(*args, snapshot=snapshot))
            return REPORT_CACHE.get(args, provider_stats.input_revision(),
                                    lambda: provider_stats.report(*args))

        body, etag, hit = await run_in_threadpool(read_local)
        # Revalidate browser copies so the reload button notices local file changes.
        headers = {"Cache-Control": "no-cache", "ETag": etag,
                   "X-Report-Cache": "HIT" if hit else "MISS"}
        candidates = [value.strip().removeprefix("W/") for value in
                      request.headers.get("if-none-match", "").split(",")]
        if etag in candidates or "*" in candidates:
            return Response(status_code=304, headers=headers)
        return Response(body, media_type="application/json", headers=headers)
    except cloud_store.StorageUnavailable as exc:
        return JSONResponse({'error': str(exc)}, status_code=503,
                            headers={'Cache-Control': 'no-store', 'Retry-After': '15'})
    except (ValueError, TypeError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400,
                            headers={"Cache-Control": "no-store"})


app = Starlette(routes=[
    Route("/", provider_page),
    Route("/providers", provider_page),
    Route("/api/providers/report", provider_report),
    Mount("/static", StaticFiles(directory=STATIC), name="static"),
])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8078)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    print(f"Football UI -> http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
