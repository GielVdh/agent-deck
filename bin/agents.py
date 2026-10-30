"""Every live coding agent on this machine, whichever app runs it, as JSON.

Claude Code is read from its own session files (below). Other agents (Codex,
Gemini, Cursor, opencode, Copilot, Amp, …) come from herdr's agent list, the
Superset snapshot, and a process scan for agent CLIs in plain terminals.

Claude Code keeps ~/.claude/sessions/<pid>.json for each running session (its
session id, cwd and a live `status`: busy, idle, waiting, blocked, needs_user,
needs_trust). The host app (Superset, herdr, Tern, a plain terminal) comes from
the process environment; title, branch and any pending question come from the
transcript tail. With --peek N, each also carries the bottom N lines of its
screen (Superset terminal, herdr pane, else the transcript's latest turns).
Stdlib only, so it can be piped over ssh."""
import glob, json, os, re, shutil, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

HOME = os.path.expanduser("~")
TAIL = 256 * 1024
ENV_KEYS = ("SUPERSET_TERMINAL_ID", "SUPERSET_WORKSPACE_ID", "HERDR_PANE_ID", "TERN_PANE")
PEEK = int(sys.argv[sys.argv.index("--peek") + 1]) if "--peek" in sys.argv else 0
SUPERSET = next((p for p in (os.path.join(HOME, ".superset/bin/superset"),) if os.path.exists(p)), shutil.which("superset"))
HERDR = shutil.which("herdr") or next((p for p in (os.path.join(HOME, ".local/bin/herdr"),) if os.path.exists(p)), None)
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07")


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def env_of(pid):
    """Only the few host-identifying variables, never anything else."""
    raw = ""
    try:
        with open(f"/proc/{pid}/environ", "rb") as fh:
            raw = fh.read().decode("utf-8", "replace").replace("\x00", " ")
    except OSError:
        try:
            raw = subprocess.run(["ps", "eww", "-o", "command=", "-p", str(pid)],
                                 capture_output=True, text=True, timeout=5).stdout
        except Exception:
            pass
    out = {}
    for tok in raw.split():
        k, _, v = tok.partition("=")
        if k in ENV_KEYS:
            out[k] = v
    return out


def ask_from(entry):
    """The question an assistant turn left open, from its last tool_use."""
    content = (entry.get("message") or {}).get("content") or []
    for block in reversed(content if isinstance(content, list) else []):
        if block.get("type") != "tool_use":
            continue
        name, inp = block.get("name"), block.get("input") or {}
        if name == "AskUserQuestion":
            qs = inp.get("questions") or []
            if qs:
                q = qs[0]
                opts = [o.get("label", "") for o in q.get("options") or []]
                return q.get("question", "") + ("\n" + "\n".join(f"{i + 1}. {o}" for i, o in enumerate(opts)) if opts else "")
        if name == "ExitPlanMode":
            return "Approve the plan?"
        detail = inp.get("command") or inp.get("file_path") or inp.get("url") or inp.get("description") or ""
        return f"Allow {name}?" + (f"\n{str(detail)[:200]}" if detail else "")
    for block in reversed(content if isinstance(content, list) else []):
        if block.get("type") == "text" and block.get("text"):
            return block["text"].strip()[-240:]
    return None


def transcript(sid):
    info = {}
    paths = glob.glob(os.path.join(HOME, ".claude", "projects", "*", f"{sid}.jsonl"))
    if not paths:
        return info
    path = paths[0]
    info["mtime"] = int(os.path.getmtime(path))
    with open(path, "rb") as fh:
        fh.seek(max(0, os.path.getsize(path) - TAIL))
        lines = fh.read().decode("utf-8", "replace").splitlines()
    for line in reversed(lines):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        t = d.get("type")
        if t == "ai-title" and "title" not in info:
            info["title"] = d.get("aiTitle")
        elif t == "custom-title" and "custom" not in info:
            info["custom"] = d.get("customTitle")
        elif t == "last-prompt" and "prompt" not in info:
            info["prompt"] = d.get("lastPrompt")
        elif t in ("user", "assistant") and not d.get("isSidechain"):
            if "branch" not in info:
                info["branch"] = d.get("gitBranch")
            if t == "assistant" and "last_assistant" not in info:
                info["last_assistant"] = d
        if all(k in info for k in ("title", "prompt", "branch", "last_assistant")):
            break
    return info


def run(argv):
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=8)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


RULE = re.compile(r"^\s*[─━]{8,}\s*$")
NOISE = re.compile(r"Update installed|Restart to update|shift\+tab to cycle|esc to interrupt|bypass permissions on|auto mode on")


def tidy(text, n, screen=False):
    lines = [ANSI.sub("", l).rstrip()[:140] for l in text.splitlines()]
    if screen:
        # drop Claude Code's own chrome: the prompt box (between the last two rules) and the status line under it
        rules = [i for i, l in enumerate(lines) if RULE.match(l)]
        if len(rules) >= 2:
            lines = lines[:rules[-2]]
        lines = [l for l in lines if not NOISE.search(l)]
    out = []
    for l in lines:
        if l.strip() or (out and out[-1].strip()):
            out.append(l)
    while out and not out[-1].strip():
        out.pop()
    return out[-n:]


def transcript_peek(sid, n):
    """No screen to read: the latest turns, written the way the terminal shows them."""
    paths = glob.glob(os.path.join(HOME, ".claude", "projects", "*", f"{sid}.jsonl"))
    if not paths:
        return []
    with open(paths[0], "rb") as fh:
        fh.seek(max(0, os.path.getsize(paths[0]) - TAIL))
        rows = fh.read().decode("utf-8", "replace").splitlines()
    out = []
    for line in rows[-400:]:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("isSidechain") or d.get("type") not in ("user", "assistant"):
            continue
        content = (d.get("message") or {}).get("content")
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        for b in content or []:
            if b.get("type") == "text" and b.get("text", "").strip():
                mark = "> " if d["type"] == "user" else "⏺ "
                for i, l in enumerate(b["text"].strip().splitlines()[:6]):
                    out.append((mark if i == 0 else "  ") + l)
            elif b.get("type") == "tool_use":
                inp = b.get("input") or {}
                arg = inp.get("command") or inp.get("file_path") or inp.get("pattern") or inp.get("description") or ""
                out.append(f"⏺ {b.get('name')}({str(arg)[:90]})")
    return tidy("\n".join(out), n)


def peek(a):
    if a["host"] == "superset" and a.get("superset_terminal") and SUPERSET:
        raw = run([SUPERSET, "terminals", "read", "--local", "--workspace", a["superset_workspace"],
                   "--terminal", a["superset_terminal"], "--max-lines", str(PEEK + 24), "--json"])
        try:
            return tidy(json.loads(raw).get("text", ""), PEEK, screen=True)
        except ValueError:
            pass
    if a["host"] == "herdr" and a.get("herdr_pane") and HERDR:
        raw = run([HERDR, "agent", "read", a["herdr_pane"], "--source", "visible", "--lines", str(PEEK + 24)])
        if raw.strip():
            return tidy(raw, PEEK, screen=True)
    return transcript_peek(a["id"], PEEK) if a.get("agent") == "claude" and a.get("id") else []


out = []
for path in glob.glob(os.path.join(HOME, ".claude", "sessions", "*.json")):
    try:
        s = json.load(open(path))
    except (OSError, ValueError):
        continue
    pid = s.get("pid")
    if not isinstance(pid, int) or not alive(pid):
        continue
    sid = s.get("sessionId")
    env = env_of(pid)
    host = ("superset" if env.get("SUPERSET_TERMINAL_ID") else "herdr" if env.get("HERDR_PANE_ID")
            else "tern" if env.get("TERN_PANE") else "terminal")
    tr = transcript(sid) if sid else {}
    status = s.get("status") or "idle"
    a = {
        "pid": pid,
        "id": sid,
        "cwd": s.get("cwd"),
        "status": status,
        "kind": s.get("kind"),
        "name": s.get("name"),
        "since": int((s.get("statusUpdatedAt") or 0) / 1000) or None,
        "host": host,
        "superset_terminal": env.get("SUPERSET_TERMINAL_ID"),
        "superset_workspace": env.get("SUPERSET_WORKSPACE_ID"),
        "herdr_pane": env.get("HERDR_PANE_ID"),
        "title": tr.get("custom") or tr.get("title") or (tr.get("prompt") or "")[:60] or s.get("name"),
        "prompt": tr.get("prompt"),
        "branch": tr.get("branch"),
        "mtime": tr.get("mtime"),
    }
    if status in ("waiting", "blocked", "needs_user", "needs_trust") and tr.get("last_assistant"):
        a["ask"] = ask_from(tr["last_assistant"])
    out.append(a)

# ---- other agents -------------------------------------------------------------
AGENT_BINS = ("codex", "gemini", "cursor-agent", "opencode", "copilot", "amp", "droid", "aider",
              "goose", "qwen", "kimi", "grok", "crush", "claude")
TITLE_GLYPHS = re.compile(r"^[\s◐◑◒◓●○✳✶✻✢·*⠁-⣿]+")


def cwd_of(pid):
    try:
        return os.readlink(f"/proc/{pid}/cwd")
    except OSError:
        pass
    raw = run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"])
    return next((l[1:] for l in raw.splitlines() if l.startswith("n")), None)


def add_other(a):
    a["status"] = a.get("status") or "idle"
    a["title"] = a.get("title") or f"{a['agent'].title()} session"
    out.append(a)


for a in out:
    a["agent"] = "claude"
seen_herdr = {a["herdr_pane"] for a in out if a.get("herdr_pane")}
seen_superset = {a["superset_terminal"] for a in out if a.get("superset_terminal")}

if HERDR:
    try:
        for h in json.loads(run([HERDR, "agent", "list"]) or "{}").get("result", {}).get("agents", []):
            if h.get("pane_id") in seen_herdr:
                continue
            seen_herdr.add(h.get("pane_id"))
            sess = h.get("agent_session") or {}
            add_other({
                "agent": h.get("agent") or "agent", "host": "herdr", "herdr_pane": h.get("pane_id"),
                "id": f"{h.get('agent')}:{sess.get('value') or h.get('pane_id')}",
                "status": h.get("agent_status"), "cwd": h.get("foreground_cwd") or h.get("cwd"),
                "title": TITLE_GLYPHS.sub("", h.get("terminal_title_stripped") or "") or None,
            })
    except ValueError:
        pass

if SUPERSET:
    try:
        snap = json.loads(run([SUPERSET, "snapshot", "--json"]) or "{}")
    except ValueError:
        snap = {}
    for w in snap.get("workspaces", []):
        for t in w.get("terminals", []):
            ag = (t.get("agent") or {})
            if not ag.get("id") or ag["id"] == "claude" or t.get("id") in seen_superset:
                continue
            seen_superset.add(t["id"])
            add_other({
                "agent": ag["id"], "host": "superset", "status": ag.get("state"),
                "id": f"{ag['id']}:{t['id']}", "superset_terminal": t["id"], "superset_workspace": w.get("id"),
                "branch": w.get("branch"), "cwd": w.get("path"),
                "title": TITLE_GLYPHS.sub("", t.get("title") or "") or w.get("name"),
            })

# agent CLIs in plain terminals (anything above already claimed its pane/terminal)
claude_pids = {a.get("pid") for a in out}
for line in run(["ps", "-A", "-o", "pid=,ppid=,command="]).splitlines():
    parts = line.split(None, 2)
    if len(parts) < 3:
        continue
    pid, ppid, cmd = int(parts[0]), int(parts[1]), parts[2]
    exe = os.path.basename(cmd.split()[0])
    if exe not in AGENT_BINS or exe == "claude" or " app-server" in cmd or pid in claude_pids:
        continue
    env = env_of(pid)
    if env.get("HERDR_PANE_ID") in seen_herdr or env.get("SUPERSET_TERMINAL_ID") in seen_superset:
        continue
    add_other({"agent": exe, "host": "tern" if env.get("TERN_PANE") else "terminal", "pid": pid,
               "id": f"{exe}:{pid}", "cwd": cwd_of(pid), "status": "idle"})

if PEEK and out:
    with ThreadPoolExecutor(max_workers=8) as pool:
        for a, lines in zip(out, pool.map(peek, out)):
            a["peek"] = lines
out.sort(key=lambda a: -(a.get("since") or 0))
json.dump({"now": int(time.time()), "agents": out}, sys.stdout)
