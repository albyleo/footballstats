"""Read-only dashboard over saved provider data. No downloads or database required.

Run: python src/webapp.py --port 8078
Feed acquisition is a separate CLI process in scripts/fetch_provider.py.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import provider_stats
import cloud_store
import premium_stats
from public_report import public_report
from excel_export import export_excel
from report_cache import ReportCache
import uvicorn
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

STATIC = Path(__file__).resolve().parent / "static"
REPORT_CACHE = ReportCache()
PREMIUM_CACHE = ReportCache(max_entries=16)


async def premium_page(request):
    return FileResponse(STATIC / 'premium.html', headers={'Cache-Control': 'no-cache'})


async def premium_report(request):
    # Central server-side access boundary; future subscriptions must be checked here.
    if os.environ.get('FOOTBALL_PREMIUM_MODE', 'open') != 'open':
        return JSONResponse({'error': 'Analisi Premium non disponibili.'}, status_code=403, headers={'Cache-Control':'no-store'})
    p = request.query_params
    try:
        if len(request.url.query) > 2048 or any(len(v) > 128 for v in p.values()):
            raise ValueError('Invalid filters')
        args = (p.get('kind','teams'),p.get('league',''),p.get('season',''),p.get('entity',''),p.get('compare',''),
                p.get('metric','xg'),p.get('venue','all'),int(p.get('last_n','0')),p.get('basis','match'),float(p.get('threshold','1')))
        def read():
            if cloud_store.enabled():
                snapshot = cloud_store.SNAPSHOTS.get()
                return PREMIUM_CACHE.get(args, ('supabase',snapshot['revision']), lambda: public_report(premium_stats.report(*args,snapshot=snapshot)))
            return PREMIUM_CACHE.get(args,provider_stats.input_revision(),lambda: public_report(premium_stats.report(*args)))
        body, etag, hit = await run_in_threadpool(read)
        headers = {'Cache-Control':'no-cache', 'ETag':etag, 'X-Report-Cache':'HIT' if hit else 'MISS'}
        if request.headers.get('if-none-match') == etag:
            return Response(status_code=304,headers=headers)
        return Response(body,media_type='application/json',headers=headers)
    except (ValueError,TypeError):
        return JSONResponse({'error':'Filtri non validi per questa analisi.'},status_code=400,headers={'Cache-Control':'no-store'})
    except cloud_store.StorageUnavailable:
        return JSONResponse({'error':'Archivio temporaneamente non disponibile.'},status_code=503,headers={'Cache-Control':'no-store'})


async def provider_page(request):
    return FileResponse(STATIC / "providers.html", headers={"Cache-Control": "no-cache"})


async def home_page(request):
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


async def documentation_page(request):
    return FileResponse(STATIC / "documentation.html", headers={"Cache-Control": "no-cache"})


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
                                        lambda: public_report(provider_stats.report(*args, snapshot=snapshot)))
            return REPORT_CACHE.get(args, provider_stats.input_revision(),
                                    lambda: public_report(provider_stats.report(*args)))

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
    except (ValueError, TypeError):
        return JSONResponse({"error": "Parametri non validi o dati non disponibili."}, status_code=400,
                            headers={"Cache-Control": "no-store"})


app = Starlette(routes=[
    Route('/premium', premium_page),
    Route('/api/premium/report', premium_report),
    Route("/", home_page),
    Route("/providers", provider_page),
    Route("/documentation", documentation_page),
    Route("/api/providers/report", provider_report),
    Route("/api/export.xlsx", export_excel, methods=["POST"]),
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
