-- Agent Deck: every live coding agent on this Mac and on your running Coder
-- workspaces as an 8-bit character in a Tern block.
-- Data comes from the Python helpers in bin/, run locally and piped over ssh to
-- each Coder workspace (`m` narrows the view to one machine).
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

local LOCAL = "local"
local MAX_ASLEEP = 18

-- The machine a tile lives on, as C.py/C.open_tab/C.sh take it: nil is this Mac.
local function remote(m: string): string?
	return if m == LOCAL then nil else m
end

-- A tile's identity: the session id (or pid), prefixed with its workspace so two
-- machines can't collide. It also picks the character, so it must stay stable.
local function agent_key(m: string, a): string
	local id = a.id or tostring(a.pid)
	return if m == LOCAL then id else m .. ":" .. id
end

-- The machines in view: all of them, or the one `m` narrowed it to.
local function in_view(s): { string }
	local out = {}
	for _, m in s.order do
		if s.view == nil or s.view == m then table.insert(out, m) end
	end
	return out
end

-- Live agents come from bin/agents.py on every machine: each running Claude Code
-- session (Superset, herdr, Tern or a plain terminal) with Claude's own status,
-- plus the other agents herdr and Superset know about.
local function tiles(s)
	local out, live, asleep = {}, {}, {}
	for _, m in in_view(s) do
		local d = s.by[m]
		if d then
			for _, a in d.agents do
				if a.id then live[m .. "|" .. a.id] = true end
				table.insert(out, { agent = a, machine = remote(m), state = C.agent_state(a.status), key = agent_key(m, a) })
			end
			for _, x in d.sessions do table.insert(asleep, { session = x, machine = remote(m), m = m }) end
		end
	end
	table.sort(out, function(x, y)
		local rx, ry = STATE_RANK[x.state] or 9, STATE_RANK[y.state] or 9
		if rx ~= ry then return rx < ry end
		return (x.agent.since or 0) > (y.agent.since or 0)
	end)
	table.sort(asleep, function(x, y) return (x.session.mtime or 0) > (y.session.mtime or 0) end)
	local n = 0
	for _, t in asleep do
		if n >= MAX_ASLEEP then break end
		if not live[t.m .. "|" .. t.session.id] then
			n += 1
			local key = if t.m == LOCAL then t.session.id else t.m .. ":" .. t.session.id
			table.insert(out, { session = t.session, machine = t.machine, state = "sleep", key = key })
		end
	end
	return out
end

-- Refreshes one machine; a machine whose ssh fails keeps its last good tiles.
local function refresh_machine(s, m: string, done: () -> ())
	local d = s.by[m]
	if not d then
		d = { agents = {}, sessions = {} }
		s.by[m] = d
	end
	if d.busy then return done() end
	d.busy = true
	local pending = 2
	local function one()
		pending -= 1
		if pending > 0 then return end
		d.busy = false
		done()
	end
	C.py(remote(m), "agents.py", { "--peek", "24" }, function(doc, err)
		d.err = err
		if doc then
			d.agents = doc.agents
			local seen = {}
			for _, a in d.agents do
				local state = C.agent_state(a.status)
				local key = agent_key(m, a)
				seen[key] = state
				-- ping once per switch into "needs you", not on the first look
				if state == "alert" and d.prev and d.prev[key] ~= "alert" then
					local _, name = C.critter(key, a.agent)
					C.notify(`{name} needs your input`, a.title or `a {agent_label(a.agent)} session is waiting`)
				end
			end
			d.prev = seen
		end
		one()
	end)
	C.py(remote(m), "sessions.py", { tostring(MAX_ASLEEP) }, function(doc, err)
		d.sessions_err = err
		if doc then d.sessions = doc.sessions end
		one()
	end)
end

local function sessions_refresh(s)
	s.loading = true
	C.render(s)
	C.machines(function(names)
		local order = { LOCAL }
		for _, n in names do table.insert(order, n) end
		s.order = order
		-- a workspace that stopped drops out of view
		for m in s.by do
			if not table.find(order, m) then s.by[m] = nil end
		end
		local pending = #order
		for _, m in order do
			refresh_machine(s, m, function()
				pending -= 1
				if pending > 0 then return end
				s.loading = false
				s.updated = os.time()
				s.sel = math.clamp(s.sel, 1, math.max(1, #tiles(s)))
				C.render(s)
			end)
		end
	end)
end

-- On a remote machine Superset's CLI may not be on PATH; it installs to ~/.superset/bin.
local REMOTE_SUPERSET = '"$(command -v superset || echo ~/.superset/bin/superset)"'

local function superset_args(a): string
	return `--local --workspace {C.shq(a.superset_workspace)} --terminal {C.shq(a.superset_terminal)}`
end

-- Opens the live session where you can type into it: a Tern tab attached to its
-- Superset terminal or herdr pane; a past session resumes with claude --resume.
local function open_tile(s, t)
	local a, x, m = t.agent, t.session, t.machine
	if a and a.host == "superset" and a.superset_terminal then
		local bin = if m then REMOTE_SUPERSET else C.shq(C.SUPERSET)
		C.open_tab(m, a.cwd, `{bin} terminals attach {superset_args(a)}`)
	elseif a and a.host == "herdr" and a.herdr_pane then
		C.open_tab(m, a.cwd, "herdr agent attach " .. C.shq(a.herdr_pane))
	elseif a then
		C.open_tab(m, a.cwd, nil)
	elseif x then
		C.open_tab(m, x.cwd, "claude --resume " .. x.id)
	end
end

-- First press arms, a second within 4 s ends the session through the app that runs it.
local function close_tile(s, t)
	local a, m, key = t.agent, t.machine, t.key
	if not a then return end
	if not (s.confirm and s.confirm.key == key and s.confirm.until_ > tern.now()) then
		s.confirm = { key = key, until_ = tern.now() + 4000 }
		tern.timer(4100, function() C.render(s) end)
		return
	end
	s.confirm = nil
	local cmd
	if a.host == "superset" and a.superset_terminal then
		local bin = if m then REMOTE_SUPERSET else C.shq(C.SUPERSET)
		cmd = `{bin} terminals close {superset_args(a)}`
	elseif a.host == "herdr" and a.herdr_pane then
		cmd = "herdr pane close " .. C.shq(a.herdr_pane)
	elseif a.pid then
		cmd = "kill -TERM " .. a.pid
	else
		return
	end
	C.sh(m, cmd, function(ok, out)
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
	if t.machine then who ..= " @ " .. t.machine end
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
		local armed = s.confirm and s.confirm.key == t.key and s.confirm.until_ > tern.now()
		table.insert(kids, C.div("dd-tile-acts", {
			C.el("div", "dd-btn go", nil, if t.state == "alert" then "Answer" else "Open", "open=" .. i),
			C.el("div", "dd-btn danger" .. (if armed then " armed" else ""), nil, if armed then "Really close?" else "Close", "close=" .. i),
		}))
	end
	return C.div("dd-tile " .. t.state .. (if i == s.sel then " sel" else ""), kids)
end

-- The machine filter: All, this Mac, each running workspace, with live counts.
local function machine_seg(s)
	local items = { { "All", s.view == nil } }
	for _, m in s.order do
		local d = s.by[m]
		table.insert(items, { if m == LOCAL then "Mac" else m, s.view == m, d and #d.agents or nil })
	end
	return C.seg(items)
end

tern.block.define("sessions", {
	init = function(cx, args, saved)
		local s = { cx = cx, sel = 1, by = {}, order = { LOCAL }, loading = false, view = saved and saved.view }
		sessions_refresh(s)
		C.every(10000, s, function() sessions_refresh(s) end)
		return s
	end,
	title = function(s)
		local need = 0
		for _, t in tiles(s) do
			if t.state == "alert" then need += 1 end
		end
		local view = if s.view == nil then "all machines" elseif s.view == LOCAL then "Mac" else s.view
		return "Sessions · " .. (if need > 0 then `{need} need{if need == 1 then "s" else ""} you` else view)
	end,
	save = function(s) return { view = s.view } end,
	view = function(s, cx)
		local all = tiles(s)
		local working, waiting = 0, {}
		for i, t in all do
			if t.state == "work" then working += 1 end
			if t.state == "alert" then table.insert(waiting, { t, i }) end
		end
		local sub = if #waiting > 0 then `{#waiting} waiting on you` elseif working > 0 then `{working} working` else "the crew"
		local kids = { C.head("✦", "Sessions", sub, { machine_seg(s) }, s.loading) }

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
		for _, m in in_view(s) do
			local d = s.by[m]
			local e = d and (d.err or d.sessions_err)
			if e then table.insert(kids, C.err((if m == LOCAL then "Mac" else m) .. ": " .. e)) end
		end

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
			dock = C.keys({ { "←↑↓→", "select" }, { "⏎", "open / answer" }, { "x", "close" }, { "n", "new claude here" }, { "m", "machines" }, { "r", "refresh" } }, s.updated),
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
			-- cycle the view: all machines → Mac → each workspace → all
			local i = if s.view == nil then 0 else (table.find(s.order, s.view) or #s.order)
			s.view, s.sel = s.order[i + 1], 1
			pcall(function() s.cx:save() end)
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
			C.open_tab(t.machine, (t.agent and t.agent.cwd) or (t.session and t.session.cwd), "claude")
			return false
		end
		return false
	end,
})

