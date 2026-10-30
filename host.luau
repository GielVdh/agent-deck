-- Agent Deck: every live coding agent on this machine (or a Coder workspace) as
-- an 8-bit character in a Tern block.
-- Data comes from the Python helpers in bin/, run locally or piped over ssh to
-- a Coder workspace (`m` switches machine).
-- Views are styled elements from common.luau; the look lives in styles.css and sprites.css.

local C = require("./common")

----------------------------------------------------------------------------
-- Sessions: every live Claude (Superset, herdr, Tern, terminal) + recent transcripts
----------------------------------------------------------------------------

local BUBBLE = {
	work = "thinking",
	idle = "your turn",
	alert = "needs you!",
	done = "done ✓",
	sleep = "zzz",
}

-- Live agents first, the ones waiting on you leading.
local STATE_RANK = { alert = 1, work = 2, done = 3, idle = 4 }

local HOST_LABEL = { superset = "Superset", herdr = "herdr", tern = "Tern", terminal = "terminal" }
local AGENT_LABEL = {
	claude = "Claude", codex = "Codex", gemini = "Gemini", ["cursor-agent"] = "Cursor", copilot = "Copilot",
	opencode = "opencode", amp = "Amp", droid = "Droid", aider = "Aider", goose = "Goose", qwen = "Qwen",
	kimi = "Kimi", grok = "Grok", crush = "Crush",
}

local function agent_label(agent: string?): string
	return AGENT_LABEL[agent or "claude"] or (agent or "agent")
end

-- Live agents come from bin/agents.py: every running Claude Code session on the
-- machine (Superset, herdr, Tern or a plain terminal), with Claude's own status.
local function tiles(s)
	local out, live = {}, {}
	for _, a in s.agents do
		if a.id then live[a.id] = true end
		table.insert(out, { agent = a, state = C.agent_state(a.status), key = a.id or tostring(a.pid) })
	end
	table.sort(out, function(x, y)
		local rx, ry = STATE_RANK[x.state] or 9, STATE_RANK[y.state] or 9
		if rx ~= ry then return rx < ry end
		return (x.agent.since or 0) > (y.agent.since or 0)
	end)
	for _, x in s.sessions do
		if not live[x.id] then table.insert(out, { session = x, state = "sleep", key = x.id }) end
	end
	return out
end

local function sessions_refresh(s)
	s.loading = true
	C.render(s)
	local pending = 2
	local function done()
		pending -= 1
		if pending > 0 then return end
		s.loading = false
		s.updated = os.time()
		s.sel = math.clamp(s.sel, 1, math.max(1, #tiles(s)))
		C.render(s)
	end
	C.py(s.machine, "agents.py", { "--peek", "24" }, function(doc, err)
		s.agent_err = err
		if doc then s.agents = doc.agents end
		local seen = {}
		for _, a in s.agents do
			local state = C.agent_state(a.status)
			local key = a.id or tostring(a.pid)
			seen[key] = state
			-- ping once per switch into "needs you", not on the first look
			if state == "alert" and s.prev and s.prev[key] ~= "alert" then
				local _, name = C.critter(a.id, a.agent)
				C.notify(`{name} needs your input`, a.title or `a {agent_label(a.agent)} session is waiting`)
			end
		end
		s.prev = seen
		done()
	end)
	C.py(s.machine, "sessions.py", { "18" }, function(doc, err)
		s.err = err
		if doc then s.sessions = doc.sessions end
		done()
	end)
	C.machines(function() end)
end

-- On a remote machine Superset's CLI may not be on PATH; it installs to ~/.superset/bin.
local REMOTE_SUPERSET = '"$(command -v superset || echo ~/.superset/bin/superset)"'

local function superset_args(a): string
	return `--local --workspace {C.shq(a.superset_workspace)} --terminal {C.shq(a.superset_terminal)}`
end

-- Opens the live session where you can type into it: a Tern tab attached to its
-- Superset terminal or herdr pane; a past session resumes with claude --resume.
local function open_tile(s, t)
	local a, x = t.agent, t.session
	if a and a.host == "superset" and a.superset_terminal then
		local bin = if s.machine then REMOTE_SUPERSET else C.shq(C.SUPERSET)
		C.open_tab(s.machine, a.cwd, `{bin} terminals attach {superset_args(a)}`)
	elseif a and a.host == "herdr" and a.herdr_pane then
		C.open_tab(s.machine, a.cwd, "herdr agent attach " .. C.shq(a.herdr_pane))
	elseif a then
		C.open_tab(s.machine, a.cwd, nil)
	elseif x then
		C.open_tab(s.machine, x.cwd, "claude --resume " .. x.id)
	end
end

-- First press arms, a second within 4 s ends the session through the app that runs it.
local function close_tile(s, t)
	local a = t.agent
	if not a then return end
	local key = a.id or tostring(a.pid)
	if not (s.confirm and s.confirm.key == key and s.confirm.until_ > tern.now()) then
		s.confirm = { key = key, until_ = tern.now() + 4000 }
		tern.timer(4100, function() C.render(s) end)
		return
	end
	s.confirm = nil
	local cmd
	if a.host == "superset" and a.superset_terminal then
		local bin = if s.machine then REMOTE_SUPERSET else C.shq(C.SUPERSET)
		cmd = `{bin} terminals close {superset_args(a)}`
	elseif a.host == "herdr" and a.herdr_pane then
		cmd = "herdr pane close " .. C.shq(a.herdr_pane)
	elseif a.pid then
		cmd = "kill -TERM " .. a.pid
	else
		return
	end
	C.sh(s.machine, cmd, function(ok, out)
		s.err = if ok then nil else "close: " .. out
		tern.timer(1500, function() sessions_refresh(s) end)
	end)
end

-- Colour a screen line the way Claude Code's own UI reads.
local function peek_class(line: string): string?
	local l = line:gsub("^%s+", "")
	if l:find("^❯") or l:find("^>") then return "you" end
	if l:find("^⏺") then return "claude" end
	if l:find("^[✻✶✢✳✽·*]") and l:find("…") then return "busy" end
	if l:find("^✓") or l:find("^✔") then return "ok" end
	if l:find("^⎿") or l:find("^※") or l:find("^[│╭╰]") then return "dim" end
	return nil
end

local function peek_view(a)
	local lines = {}
	for _, l in a.peek do table.insert(lines, C.el("span", peek_class(l), nil, if l == "" then " " else l)) end
	local where = agent_label(a.agent) .. " · " .. (({ superset = "Superset", herdr = "herdr" })[a.host] or "transcript")
	return C.div("dd-peek", {
		C.div("dd-peek-h", { C.el("span", "dd-dot"), C.t(nil, where), C.t("ttl", a.title or ""), C.t("sp", ""), C.t(nil, "click to open ↗") }),
		C.div("dd-peek-b", lines),
	})
end

local function tile_view(s, t, i: number)
	local x, a = t.session, t.agent
	local _, name = C.critter(t.key, a and a.agent)
	local title = (a and a.title) or (x and x.title) or agent_label(a and a.agent)
	local cwd = (a and a.cwd) or (x and x.cwd)
	local branch = (a and a.branch) or (x and x.branch)
	local where = C.short_path(cwd):match("[^/]+$") or "~"

	local bubble = { C.t(nil, BUBBLE[t.state] or t.state) }
	if t.state == "work" then table.insert(bubble, C.t("dd-dots", "...")) end
	local stage = {
		C.sprite(t.key, t.state, "lg", a and a.agent),
		C.div("dd-bubble " .. t.state, bubble),
	}
	local age = if a then a.since else x and x.mtime
	if age then table.insert(stage, C.t("dd-age", C.ago(age))) end

	local line = { C.chip(where, if a then "accent" else "muted") }
	if branch and branch ~= "HEAD" and branch ~= where then table.insert(line, C.t("dd-ell dd-mono dd-dim", "⎇ " .. branch)) end
	local who = if a then "· " .. (if a.agent ~= "claude" then agent_label(a.agent) .. " · " else "") .. (HOST_LABEL[a.host] or a.host) else "· asleep"
	local body = {
		C.div("dd-agent-name", { C.t(nil, name), C.t("who", who) }),
		C.t("dd-tile-title", title),
		C.div("dd-line", line),
	}
	if t.state == "alert" and a and a.ask then table.insert(body, C.t("dd-ask", a.ask)) end

	local main = { C.div("dd-tile-stage", stage), C.div("dd-tile-body", body) }
	if a and a.peek and #a.peek > 0 then table.insert(main, peek_view(a)) end
	local kids = { C.el("div", "dd-tile-main", main, nil, "open=" .. i) }
	if a then
		local armed = s.confirm and s.confirm.key == (a.id or tostring(a.pid)) and s.confirm.until_ > tern.now()
		table.insert(kids, C.div("dd-tile-acts", {
			C.el("div", "dd-btn go", nil, if t.state == "alert" then "Answer" else "Open", "open=" .. i),
			C.el("div", "dd-btn danger" .. (if armed then " armed" else ""), nil, if armed then "Really close?" else "Close", "close=" .. i),
		}))
	end
	return C.div("dd-tile " .. t.state .. (if i == s.sel then " sel" else ""), kids)
end

tern.block.define("sessions", {
	init = function(cx, args, saved)
		local s = { cx = cx, sel = 1, agents = {}, sessions = {}, loading = false, machine = saved and saved.machine }
		sessions_refresh(s)
		C.every(10000, s, function() sessions_refresh(s) end)
		return s
	end,
	title = function(s)
		local need = 0
		for _, a in s.agents do
			if C.agent_state(a.status) == "alert" then need += 1 end
		end
		return "Sessions · " .. (if need > 0 then `{need} need{if need == 1 then "s" else ""} you` else (s.machine or "local"))
	end,
	save = function(s) return { machine = s.machine } end,
	view = function(s, cx)
		local all = tiles(s)
		local working, waiting = 0, {}
		for i, t in all do
			if t.state == "work" then working += 1 end
			if t.state == "alert" then table.insert(waiting, { t, i }) end
		end
		local sub = if #waiting > 0 then `{#waiting} waiting on you` elseif working > 0 then `{working} working` else "the crew"
		local kids = { C.head("✦", "Sessions", sub, { C.machine_seg(s.machine) }, s.loading) }

		if #waiting > 0 then
			local names = {}
			for _, w in waiting do
				local _, n = C.critter(w[1].key, w[1].agent and w[1].agent.agent)
				table.insert(names, n)
			end
			table.insert(kids, C.el("div", "dd-alarm-bar", {
				C.t("bell", "🔔"),
				C.t(nil, table.concat(names, ", ") .. (if #names == 1 then " needs" else " need") .. " your input"),
				C.t("hint", "click or ⏎ to answer"),
			}, nil, "open=" .. waiting[1][2]))
		end
		if s.err then table.insert(kids, C.err(s.err)) end
		if s.agent_err then table.insert(kids, C.err("live sessions: " .. s.agent_err)) end

		local live, asleep = {}, {}
		for i, t in all do
			table.insert(if t.agent then live else asleep, tile_view(s, t, i))
		end
		table.insert(kids, C.group("On stage", #live, {
			if #live > 0 then C.div("dd-tiles", live) else C.empty("nobody's on shift — pick a session below and press n to start one"),
		}))
		table.insert(kids, C.group("Asleep · recent sessions", #asleep, {
			if #asleep > 0 then C.div("dd-tiles", asleep) else C.empty(if s.loading then "loading…" else "no sessions"),
		}))

		return {
			main = C.page(kids),
			dock = C.keys({ { "←↑↓→", "select" }, { "⏎", "open / answer" }, { "x", "close" }, { "n", "new claude here" }, { "m", "machine" }, { "r", "refresh" } }, s.updated),
		}
	end,
	event = function(s, ev, cx)
		tern.log.debug("agent-deck sessions event", tern.json.encode(ev))
		if ev.ev ~= "action" then return end
		local i = tonumber(ev.value)
		local t = i and tiles(s)[i]
		if not t then return end
		s.sel = i
		if ev.act == "open" then
			open_tile(s, t)
		elseif ev.act == "close" then
			close_tile(s, t)
		end
		C.render(s)
	end,
	key = function(s, key, cx)
		local all = tiles(s)
		local k = key.name
		-- tiles sit 3 to a row: ←/→ step one, ↑/↓ a whole row
		local step = { left = -1, h = -1, right = 1, l = 1, up = -3, k = -3, down = 3, j = 3 }
		if step[k] then
			s.sel = math.clamp(s.sel + step[k], 1, math.max(1, #all))
			return true
		end
		if C.nav(s, key, #all) then return true end
		local t = all[s.sel]
		if k == "r" then
			sessions_refresh(s)
			return true
		elseif k == "m" then
			C.next_machine(s.machine, function(m)
				s.machine, s.sel, s.agents, s.sessions, s.prev = m, 1, {}, {}, nil
				pcall(function() s.cx:save() end)
				sessions_refresh(s)
			end)
			return true
		elseif not t then
			return false
		elseif k == "enter" then
			open_tile(s, t)
			return false
		elseif k == "x" then
			close_tile(s, t)
			return true
		elseif k == "n" then
			C.open_tab(s.machine, (t.agent and t.agent.cwd) or (t.session and t.session.cwd), "claude")
			return false
		end
		return false
	end,
})

