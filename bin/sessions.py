"""Recent Claude Code sessions as JSON: title, last prompt, cwd, branch, age.
Reads only the tail of each transcript so it stays fast on large sessions."""
import glob, json, os, sys, time

LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 12
TAIL = 256 * 1024
root = os.path.expanduser("~/.claude/projects")
files = sorted(glob.glob(os.path.join(root, "*", "*.jsonl")), key=os.path.getmtime, reverse=True)

out = []
for path in files[:LIMIT]:
    s = {"id": os.path.basename(path)[:-6], "mtime": int(os.path.getmtime(path))}
    with open(path, "rb") as fh:
        fh.seek(max(0, os.path.getsize(path) - TAIL))
        lines = fh.read().decode("utf-8", "replace").splitlines()
    for line in reversed(lines):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        t = d.get("type")
        if t == "ai-title" and "title" not in s:
            s["title"] = d.get("aiTitle")
        elif t == "custom-title" and "custom" not in s:
            s["custom"] = d.get("customTitle")
        elif t == "last-prompt" and "prompt" not in s:
            s["prompt"] = d.get("lastPrompt")
        elif t in ("user", "assistant") and "cwd" not in s and d.get("cwd"):
            s["cwd"] = d["cwd"]
            s["branch"] = d.get("gitBranch")
        if all(k in s for k in ("title", "prompt", "cwd")):
            break
    s["title"] = s.pop("custom", None) or s.get("title") or (s.get("prompt") or "")[:60] or s["id"][:8]
    out.append(s)
json.dump({"now": int(time.time()), "sessions": out}, sys.stdout)
