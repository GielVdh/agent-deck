-- Shared plumbing for the Agent Deck blocks: running helpers (locally or over
-- ssh on a Coder workspace), opening tabs, selection, formatting, and the
-- styled elements the views are built from (classes live in styles.css).

local ui = tern.ui
local M = {}

local HOME = tern.getenv("HOME") or ""
local BIN_DIRS = { HOME .. "/.local/bin", "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", HOME .. "/.superset/bin", "/Applications/Tern.app/Contents/MacOS" }
local PATH = table.concat(BIN_DIRS, ":") .. ":/usr/sbin:/sbin"
M.HOME = HOME

-- First existing `name` in the usual install dirs, else the bare name.
function M.find_bin(name: string): string
	for _, dir in BIN_DIRS do
		if tern.fs.exists(dir .. "/" .. name) then return dir .. "/" .. name end
	end
	return name
end
M.TERN = M.find_bin("tern")
M.SUPERSET = M.find_bin("superset")

-- Optional config.json next to plugin.toml (see config.example.json); every key has a default.
local CONFIG = { ssh_host = "coder.{name}" }
do
	local ok, raw = pcall(tern.fs.read, "config.json")
	local good, doc = if ok then pcall(tern.json.decode, raw) else false, nil
	if good and type(doc) == "table" then
		for k, v in doc do CONFIG[k] = v end
	end
end
M.config = CONFIG

-- The ssh host of a Coder workspace (`coder config-ssh` names them coder.<workspace>).
function M.ssh_host(machine: string): string
	return (CONFIG.ssh_host:gsub("{name}", machine))
end

----------------------------------------------------------------------------
-- processes
----------------------------------------------------------------------------

-- Runs argv; cb(ok, stdout | error text).
function M.run(argv: { string }, opts: any?, cb: (boolean, string) -> ())
	local o = opts or {}
	o.env = o.env or { PATH = PATH }
	o.cwd = o.cwd or "."
	o.timeout_ms = o.timeout_ms or 90000
	local ok, err = pcall(tern.process.run, argv, o, function(r)
		if r.status == 0 then
			cb(true, r.stdout)
		else
			local msg = if r.timed_out then "timed out" elseif r.stderr ~= "" then r.stderr else r.stdout
			cb(false, (msg:gsub("%s+$", "")):sub(1, 300))
		end
	end)
	if not ok then cb(false, tostring(err)) end
end

-- Runs argv and decodes its stdout as JSON; a top-level `error` field is an error.
function M.json(argv: { string }, opts: any?, cb: (any?, string?) -> ())
	M.run(argv, opts, function(ok, out)
		if not ok then return cb(nil, out) end
		local good, doc = pcall(tern.json.decode, out)
		if not good then return cb(nil, "bad JSON: " .. out:sub(1, 200)) end
		if type(doc) == "table" and doc.error then return cb(nil, tostring(doc.error)) end
		cb(doc, nil)
	end)
end

local function ssh_argv(machine: string): { string }
	return { "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", M.ssh_host(machine) }
end

-- Runs bin/<script> locally, or pipes it to python3 on a Coder workspace.
function M.py(machine: string?, script: string, args: { string }?, cb: (any?, string?) -> ())
	local argv
	local opts = {}
	if machine then
		argv = ssh_argv(machine)
		table.insert(argv, "python3")
		table.insert(argv, "-")
		opts.stdin = tern.fs.read("bin/" .. script)
	else
		argv = { "python3", "-I", "bin/" .. script }
	end
	for _, a in args or {} do table.insert(argv, a) end
	M.json(argv, opts, cb)
end

local function shq(s: string): string
	return "'" .. s:gsub("'", "'\\''") .. "'"
end
M.shq = shq

-- Opens a Tern tab in `dir` on `machine` (nil = this Mac) running `cmd` (a shell string), else a shell.
function M.open_tab(machine: string?, dir: string?, cmd: string?)
	local argv = { M.TERN, "new", "tab" }
	if machine then
		local remote = (if dir then "cd " .. shq(dir) .. " && " else "") .. "exec " .. (cmd or "$SHELL -l")
		for _, a in { "--keep-open", "--", M.TERN, "ssh", M.ssh_host(machine), "-t", remote } do table.insert(argv, a) end
	else
		if dir then
			table.insert(argv, "--cwd")
			table.insert(argv, dir)
		end
		if cmd then
			for _, a in { "--keep-open", "--", "/bin/zsh", "-lc", cmd } do table.insert(argv, a) end
		end
	end
	M.run(argv, nil, function() end)
end

-- Running Coder workspaces, cached for a minute; cb({ names }).
local machine_cache = { at = -math.huge, names = {} }
function M.machines(cb: ({ string }) -> ())
	if tern.now() - machine_cache.at < 60000 then return cb(machine_cache.names) end
	M.py(nil, "coder.py", nil, function(doc)
		local names = {}
		for _, w in (doc and doc.workspaces or {}) do
			if w.status == "running" then table.insert(names, w.name) end
		end
		machine_cache = { at = tern.now(), names = names }
		cb(names)
	end)
end

-- Re-arms `fn` every `ms` while the block's cx is still alive.
function M.every(ms: number, s: any, fn: () -> ())
	tern.timer(ms, function()
		if not pcall(function() return s.cx.pane end) then return end
		fn()
		M.every(ms, s, fn)
	end)
end

function M.render(s: any)
	pcall(function() s.cx:render() end)
end

----------------------------------------------------------------------------
-- formatting + selection
----------------------------------------------------------------------------

-- Seconds since epoch of an RFC 3339 UTC timestamp.

function M.ago(ts: number?): string
	if not ts or ts == 0 then return "" end
	local d = os.time() - ts
	if d < 60 then return "now" end
	if d < 3600 then return `{d // 60}m` end
	if d < 86400 then return `{d // 3600}h` end
	return `{d // 86400}d`
end

function M.short_path(p: string?): string
	if not p then return "" end
	return (p:gsub("^" .. HOME:gsub("%-", "%%-"), "~"):gsub("^/home/coder", "~"))
end

-- j/k/↑/↓/g/G over `n` rows; returns true when the key moved the selection.
function M.nav(s: any, key: any, n: number): boolean
	local k = key.name
	if k == "j" or k == "down" then
		s.sel = math.min(n, s.sel + 1)
	elseif k == "k" or k == "up" then
		s.sel = math.max(1, s.sel - 1)
	elseif k == "g" or k == "home" then
		s.sel = 1
	elseif k == "G" or k == "end" then
		s.sel = math.max(1, n)
	else
		return false
	end
	return true
end

-- The dock: native key caps and the last update time.
function M.keys(pairs: { { string } }, updated: number?)
	local spans = {}
	for _, p in pairs do
		table.insert(spans, ui.span(p[1], "key"))
		table.insert(spans, " " .. p[2] .. "   ")
	end
	if updated then table.insert(spans, ui.span("updated " .. os.date("%H:%M:%S", updated), "muted")) end
	return ui.text(spans)
end

----------------------------------------------------------------------------
-- styled elements
----------------------------------------------------------------------------

-- `act` makes the element clickable (Tern only honours `actions = { click = act }`):
-- a click arrives as {ev = "action", act, value}
-- ("open=3" splits into act "open", value "3").
local function el(tag: string, cls: string?, children: { any }?, text: string?, act: string?)
	local p: any = {}
	if cls then p.class = cls end
	if text then p.text = text end
	if act then p.actions = { click = act } end
	return ui.el(tag, p, children)
end
M.el = el

function M.div(cls: string, children: { any }?)
	return el("div", cls, children)
end

function M.t(cls: string?, text: string)
	return el("span", cls, nil, text)
end

-- A pill; tone is ok/warn/bad/live/accent/muted; `dot` adds a status dot.
function M.chip(text: string, tone: string?, dot: boolean?, extra: string?)
	local kids = {}
	if dot then table.insert(kids, el("span", "dd-dot")) end
	table.insert(kids, el("span", nil, nil, text))
	return el("span", "dd-chip " .. (tone or "muted") .. (if extra then " " .. extra else ""), kids)
end

local function hash(s: string): number
	local h = 0
	for i = 1, #s do h = (h * 31 + s:byte(i)) % 2147483647 end
	return h
end

-- Header bar: icon, title, subtitle, a spinner while loading, then right-aligned nodes.
function M.head(icon: string, title: string, sub: string?, right: { any }?, loading: boolean?)
	local kids = { el("span", "dd-ic", nil, icon), el("span", "dd-title", nil, title) }
	if sub then table.insert(kids, el("span", "dd-sub", nil, sub)) end
	if loading then table.insert(kids, el("span", "dd-spin")) end
	table.insert(kids, el("span", "dd-sp"))
	for _, r in right or {} do table.insert(kids, r) end
	return el("div", "dd-head", kids)
end

-- Segmented control: { {label, on, count?} }.
function M.seg(items: { any })
	local kids = {}
	for _, it in items do
		local inner = { el("span", nil, nil, it[1]) }
		if it[3] then table.insert(inner, el("span", "n", nil, tostring(it[3]))) end
		table.insert(kids, el("span", "dd-seg-i" .. (if it[2] then " on" else ""), inner))
	end
	return el("div", "dd-seg", kids)
end

function M.group(head: string, n: number?, children: { any })
	local h = { el("span", nil, nil, head) }
	if n then table.insert(h, el("span", "n", nil, tostring(n))) end
	local kids = { el("div", "dd-group-h", h) }
	for _, c in children do table.insert(kids, c) end
	return el("div", "dd-group", kids)
end

function M.empty(text: string)
	return el("div", "dd-empty", nil, text)
end

function M.err(text: string)
	return el("div", "dd-err", nil, text)
end

-- The block's main region: everything inside one .dd column.
function M.page(children: { any })
	return ui.col({ el("div", "dd", children) })
end

-- 8-bit Claudes (sprites.css). Each key (a Claude session id) gets a stable hat and name.
local CRITTERS = {
	{ "wizard", "Merlin" },
	{ "party", "Confetti" },
	{ "tophat", "Sir Tokens" },
	{ "crown", "Queen Context" },
	{ "propeller", "Zippy" },
	{ "chef", "Chef Prompt" },
	{ "cowboy", "Tex" },
	{ "viking", "Bjorn" },
	{ "cap", "Coach" },
	{ "beanie", "Pom" },
}

-- The other agents' five looks each (sprites.css .v0–.v4), named in that order.
local VARIANT_NAMES = {
	codex = { "Prompt", "Amber", "BSOD", "Retro", "Neo" },
	gemini = { "Twinkle", "Rosé", "Lagoon", "Gilded", "Halo" },
	copilot = { "Maverick", "Goose", "Iceman", "Red Baron", "Mint Julep" },
	["cursor-agent"] = { "Cubert", "Midnight", "Goldie", "Minty", "Rosie" },
	opencode = { "Brace", "Lime", "Sky", "Rosa", "Slate" },
	robot = { "Bolt", "Brass", "Navi", "Sprout", "Rusty" },
}

-- A session's look and name: a hat for Claude, a variant (0–4) for other agents.
function M.critter(key: string?, agent: string?): (string, string)
	if agent and agent ~= "claude" then
		local names = VARIANT_NAMES[agent] or VARIANT_NAMES.robot
		local v = hash(key or "?") % #names
		return "v" .. v, names[v + 1]
	end
	local c = CRITTERS[hash(key or "?") % #CRITTERS + 1]
	return c[1], c[2]
end

-- Agents with a character of their own in sprites.css; any other agent is drawn as the robot.
local OWN_SPRITE = { codex = "codex", gemini = "gemini", copilot = "copilot", ["cursor-agent"] = "cursoragent", opencode = "opencode" }

-- state: work | idle | alert | sleep; size: nil | "sm" | "lg"; non-Claude agents get their own character.
function M.sprite(key: string?, state: string, size: string?, agent: string?)
	local hat = M.critter(key)
	local cls = "cl-w st-" .. state .. (if size then " " .. size else "")
	if agent and agent ~= "claude" then cls ..= " ag-" .. (OWN_SPRITE[agent] or "robot") .. " " .. M.critter(key, agent) end
	return el("span", cls, {
		el("span", "cl-b", {
			el("span", "cl"),
			el("span", "cl-eyes"),
			el("span", "cl-hat hat-" .. hat),
		}),
	})
end

-- herdr agent_status → sprite state.
-- A live status (Claude Code's own: busy/shell/idle/waiting/blocked/needs_user/needs_trust,
-- herdr's: working/blocked/idle/done, or Superset's) → sprite state.
local STATES = {
	busy = "work", shell = "work", working = "work", running = "work", thinking = "work",
	waiting = "alert", blocked = "alert", needs_user = "alert", needs_trust = "alert", permission = "alert",
	needs_input = "alert", input = "alert", attention = "alert",
	done = "done",
}
function M.agent_state(status: string?): string
	return STATES[status or ""] or "idle"
end

-- Runs a shell command line on `machine` over ssh, or locally through a login shell.
function M.sh(machine: string?, cmd: string, cb: ((boolean, string) -> ())?)
	local argv = if machine then ssh_argv(machine) else { "/bin/zsh", "-lc" }
	table.insert(argv, cmd)
	M.run(argv, { timeout_ms = 30000 }, cb or function() end)
end

-- A macOS notification (with sound), for things that need you.
function M.notify(title: string, body: string)
	local function q(x: string) return '"' .. x:gsub('[\\"]', "") .. '"' end
	M.run({ "osascript", "-e", `display notification {q(body)} with title {q(title)} sound name "Glass"` }, nil, function() end)
end

return M
