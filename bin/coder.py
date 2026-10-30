"""My Coder workspaces as compact JSON (the raw `coder list -o json` is huge)."""
import json, os, subprocess, sys, time

CODER = next((c for c in ("/opt/homebrew/bin/coder", "/usr/local/bin/coder") if os.path.exists(c)), "coder")

r = subprocess.run([CODER, "list", "--search", "owner:me", "-o", "json"],
                   capture_output=True, text=True, timeout=30)
if r.returncode != 0:
    json.dump({"error": (r.stderr or r.stdout).strip()[:400]}, sys.stdout)
    sys.exit(0)

url = ""
for p in ("~/Library/Application Support/coderv2/url", "~/.config/coderv2/url"):
    p = os.path.expanduser(p)
    if os.path.exists(p):
        url = open(p).read().strip().rstrip("/")
        break

out = []
for w in json.loads(r.stdout or "[]"):
    b = w.get("latest_build") or {}
    agents = [a for res in b.get("resources") or [] for a in res.get("agents") or []]
    a = agents[0] if agents else {}
    app = w.get("latest_app_status") or {}
    out.append({
        "name": w["name"],
        "owner": w.get("owner_name"),
        "template": w.get("template_display_name") or w.get("template_name"),
        "status": b.get("status"),
        "transition": b.get("transition"),
        "outdated": w.get("outdated", False),
        "healthy": (w.get("health") or {}).get("healthy", True),
        "last_used": w.get("last_used_at"),
        "deadline": b.get("deadline"),
        "daily_cost": b.get("daily_cost", 0),
        "agent": a.get("status"),
        "lifecycle": a.get("lifecycle_state"),
        "apps": [x.get("display_name") or x.get("slug") for x in a.get("apps") or []],
        "app_status": app.get("message"),
        "app_state": app.get("state"),
        "url": f"{url}/@{w.get('owner_name')}/{w['name']}" if url else None,
    })
json.dump({"now": int(time.time()), "workspaces": out}, sys.stdout)
