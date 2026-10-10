"""Write an offline per-fixture half-time audit; never calls providers."""
import json
from pathlib import Path
import sys
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import provider_stats


if __name__ == "__main__":
    rows = provider_stats.report(kind="teams", metric="first-half-goals")["halftime_audit"]
    target = ROOT / "artifacts" / "halftime-audit.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(dict(Counter(r["status"] for r in rows))))
    print(f"First-half stoppage-time goals cross-checked: {sum(r['stoppage_goals'] for r in rows)}")
    print(f"Saved {target}")
