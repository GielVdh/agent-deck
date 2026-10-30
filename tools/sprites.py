"""Generates sprites.css: 8-bit Claude critters drawn with box-shadow pixel art.

A sprite is .cl-w (size, scale) > .cl-b (motion) > three stacked spans: .cl
(body + legs), .cl-eyes and .cl-hat.hat-<name>. Each layer is one 3px element whose box-shadows paint the
pixels, so a whole critter is five DOM nodes. State classes on .cl-w
(st-work, st-idle, st-alert, st-sleep) pick the animations.

Run: python3 tools/sprites.py > sprites.css
"""

PX = 3  # CSS pixels per sprite pixel
W, H = 12, 12

PALETTE = {
    "O": "#d97757",  # Claude orange
    "D": "#b4573a",  # shade
    "K": "#1c1917",
    "J": "#57534e",  # charcoal, for dark hats on dark themes
    "W": "#f5f5f4",
    "Y": "#facc15",
    "P": "#ec4899",
    "U": "#7c3aed",
    "R": "#ef4444",
    "B": "#3b82f6",
    "G": "#22c55e",
    "N": "#92400e",
    "S": "#a8a29e",
    "C": "#22d3ee",
    "g": "#10a37f",  # codex green
    "X": "#0b1220",  # screen
    "L": "#e5e7eb",  # light grey
    "M": "#9ca3af",  # mid grey
    "A": "#f5a524",  # amber
    "V": "#a78bfa",  # violet
}

# rows 5..11 of the 12x12 grid; legs alternate between two frames
BODY = [
    ".OOOOOOOOOO.",
    ".OOOOOOOOOO.",
    "OOOOOOOOOOOO",
    "OOOOOOOOOOOO",
    ".OOOOOOOOOO.",
    ".DDDDDDDDDD.",
]
LEGS_A = ".D.D....D.D."
LEGS_B = "..D.D..D.D.."

EYES_OPEN = {7: "...KW...KW..", 8: "...KK...KK.."}
EYES_BLINK = {8: "...KK...KK.."}
EYES_SHUT = {8: "..KK....KK.."}

# rows 0..4, sitting on the body's top row
HATS = {
    "wizard": [
        "......Y.....",
        ".....UU.....",
        "....UUYU....",
        "...UUUUUU...",
        ".UUUUUUUUUU.",
    ],
    "party": [
        "......W.....",
        "......P.....",
        ".....YPY....",
        "....PYPYP...",
        "...YPYPYPY..",
    ],
    "tophat": [
        "............",
        "...JJJJJJ...",
        "...JJJJJJ...",
        "...RRRRRR...",
        ".JJJJJJJJJJ.",
    ],
    "crown": [
        "............",
        "..Y..Y..Y...",
        "..YY.YY.YY..",
        "..YYYYYYYY..",
        "..YRYYBYYRY.",
    ],
    "propeller": [
        "...RRR.BBB..",
        "......K.....",
        "....GRGRG...",
        "...RGRGRGR..",
        "..RRRRRRRR..",
    ],
    "chef": [
        "...WW.WW....",
        "..WWWWWWW...",
        "..WWWWWWW...",
        "...WWWWW....",
        "...WWWWW....",
    ],
    "cowboy": [
        "............",
        "....NNNN....",
        "...NNNNNN...",
        "...NJJJJN...",
        "NNNNNNNNNNNN",
    ],
    "viking": [
        "............",
        "W..........W",
        "WW..SSSS..WW",
        ".WSSSSSSSSW.",
        "..SYSSSSYS..",
    ],
    "cap": [
        "............",
        "............",
        "...BBBBB....",
        "..BBBWBBB...",
        "..BBBBBBBBBB",
    ],
    "beanie": [
        ".....W......",
        "....CCC.....",
        "...CCCCC....",
        "..CCCCCCC...",
        "..WWWWWWWW..",
    ],
}
PROPELLER_SPIN = "...BBB.RRR.."  # the propeller's second frame

# Accessories drawn in the (otherwise hidden) hat layer of non-Claude characters.
ACCESSORIES = {
    "headphones": {1: "...SSSSSS...", 2: "..S......S..", 3: ".S........S.", 4: "RR........RR", 5: "RR........RR", 6: "RR........RR"},
    "halo": {0: "...YYYYYY...", 1: "..Y......Y..", 2: "...YYYYYY..."},
    "scarf": {8: ".WWWWWWWWWW.", 9: ".......WW...", 10: "........WW.."},
    "bowtie": {9: "....R..R....", 10: "....RRRR....", 11: "....R..R...."},
}

# Five looks per agent: name, palette overrides, accessory. Picked per session.
VARIANTS = {
    "codex": [
        ("Prompt", {}, None),
        ("Amber", {"g": "#f59e0b"}, None),
        ("BSOD", {"X": "#1d4ed8", "g": "#f1f5f9"}, None),
        ("Retro", {"M": "#c8b892", "L": "#efe6cf", "g": "#22c55e"}, None),
        ("Neo", {"g": "#4ade80", "M": "#3f3f46", "L": "#71717a"}, "headphones"),
    ],
    "gemini": [
        ("Twinkle", {}, None),
        ("Rosé", {"B": "#ec4899", "V": "#fbcfe8"}, None),
        ("Lagoon", {"B": "#14b8a6", "V": "#99f6e4"}, None),
        ("Gilded", {"B": "#eab308", "V": "#fef08a"}, None),
        ("Halo", {"B": "#8b5cf6", "V": "#ddd6fe"}, "halo"),
    ],
    "copilot": [
        ("Maverick", {}, None),
        ("Goose", {"U": "#27272a", "L": "#a5f3fc"}, None),
        ("Iceman", {"U": "#0ea5e9", "L": "#f0f9ff"}, None),
        ("Red Baron", {"U": "#dc2626", "L": "#fde68a"}, "scarf"),
        ("Mint Julep", {"U": "#10b981", "L": "#d1fae5"}, None),
    ],
    "cursor-agent": [
        ("Cubert", {}, None),
        ("Midnight", {"L": "#a5b4fc", "M": "#6366f1", "J": "#3730a3"}, None),
        ("Goldie", {"L": "#fde68a", "M": "#f59e0b", "J": "#b45309"}, None),
        ("Minty", {"L": "#a7f3d0", "M": "#10b981", "J": "#047857"}, None),
        ("Rosie", {"L": "#fbcfe8", "M": "#ec4899", "J": "#9d174d"}, "bowtie"),
    ],
    "opencode": [
        ("Brace", {}, None),
        ("Lime", {"A": "#84cc16", "N": "#3f6212"}, None),
        ("Sky", {"A": "#38bdf8", "N": "#075985"}, None),
        ("Rosa", {"A": "#fb7185", "N": "#9f1239"}, None),
        ("Slate", {"A": "#94a3b8", "N": "#334155"}, "headphones"),
    ],
    "robot": [
        ("Bolt", {}, None),
        ("Brass", {"M": "#d4a64a", "L": "#f3e1b0", "C": "#fde047"}, None),
        ("Navi", {"M": "#475569", "L": "#94a3b8", "C": "#38bdf8", "R": "#f43f5e"}, None),
        ("Sprout", {"M": "#86efac", "L": "#dcfce7", "C": "#166534", "R": "#16a34a"}, None),
        ("Rusty", {"M": "#b45309", "L": "#fdba74", "C": "#fef3c7"}, "headphones"),
    ],
}

# Other agents: full 12x11 bodies (row 11 is the legs, two frames), eyes layers,
# a blink frame and shut (asleep) eyes. Rows not listed are empty.
OTHERS = {
    # a little CRT terminal-bot with a green >_ face; its cursor blinks
    "codex": {
        "body": [
            "......g.....",
            "......M.....",
            ".MMMMMMMMMM.",
            ".MXXXXXXXXM.",
            ".MXXXXXXXXM.",
            ".MXXXXXXXXM.",
            ".MXXXXXXXXM.",
            ".MMMMMMMMMM.",
            "..LLLLLLLL..",
            "...MMMMMM...",
            "............",
        ],
        "legs": ("..M.M..M.M..", "...M.M.M.M.."),
        "eyes": {4: "...g........", 5: "....g.......", 6: "...g..gg...."},
        "blink": {4: "...g........", 5: "....g.......", 6: "...g........"},
        "shut": {6: "...gg.gg...."},
        "blink_s": 1.2,
    },
    # a blue four-point sparkle
    "gemini": {
        "body": [
            ".....BB.....",
            ".....BB.....",
            "....BBBB....",
            "...BBBBBB...",
            "..BBBVVBBB..",
            "BBBBVVVVBBBB",
            "BBBBVVVVBBBB",
            "..BBBVVBBB..",
            "...BBBBBB...",
            "....BBBB....",
            ".....BB.....",
        ],
        "legs": ("....B..B....", ".....BB....."),
        "eyes": {5: "...KW..KW...", 6: "...KK..KK..."},
        "blink": {6: "...KK..KK..."},
        "shut": {6: "..KK....KK.."},
    },
    # round purple head with big pilot goggles
    "copilot": {
        "body": [
            "............",
            "...UUUUUU...",
            "..UUUUUUUU..",
            ".UUUUUUUUUU.",
            ".ULLLUULLLU.",
            ".ULLLUULLLU.",
            ".ULLLUULLLU.",
            ".UUUUUUUUUU.",
            "..UUUUUUUU..",
            "...UUUUUU...",
            "............",
        ],
        "legs": ("..U.U..U.U..", "...U.U.U.U.."),
        "eyes": {5: "...K....K...", 6: "...K....K..."},
        "blink": {6: "...K....K..."},
        "shut": {6: "..KK...KK..."},
    },
    # an isometric cube
    "cursor-agent": {
        "body": [
            "............",
            ".....LL.....",
            "...LLLLLL...",
            ".LLLLLLLLLL.",
            ".MMMLLLLJJJ.",
            ".MMMMMJJJJJ.",
            ".MMMMMJJJJJ.",
            ".MMMMMJJJJJ.",
            ".MMMMMJJJJJ.",
            "...MMMJJJ...",
            ".....MJ.....",
        ],
        "legs": ("...M....J...", "....M..J...."),
        "eyes": {6: "..K....W....", 7: "..K....W...."},
        "blink": {7: "..K....W...."},
        "shut": {7: ".KK....WW..."},
    },
    # an amber block with { } eyes
    "opencode": {
        "body": [
            "............",
            "............",
            ".AAAAAAAAAA.",
            ".AAAAAAAAAA.",
            ".AAAAAAAAAA.",
            ".AAAAAAAAAA.",
            ".AAAAAAAAAA.",
            ".AAAAAAAAAA.",
            ".AAAAAAAAAA.",
            ".NNNNNNNNNN.",
            "............",
        ],
        "legs": ("..N.N..N.N..", "...N.N.N.N.."),
        "eyes": {4: "...KK..KK...", 5: "..K......K..", 6: "...KK..KK..."},
        "blink": {5: "..K......K.."},
        "shut": {5: "..KKK..KKK.."},
    },
    # any other agent: a grey robot with a visor
    "robot": {
        "body": [
            ".....R......",
            ".....M......",
            "..MMMMMMMM..",
            ".MMMMMMMMMM.",
            ".MMXXXXXXMM.",
            ".MMXXXXXXMM.",
            ".MMMMMMMMMM.",
            ".MMLLLLLLMM.",
            "..MMMMMMMM..",
            "...MM..MM...",
            "............",
        ],
        "legs": ("...M....M...", "....M..M...."),
        "eyes": {4: "....C..C....", 5: "....C..C...."},
        "blink": {5: "....C..C...."},
        "shut": {5: "....CC.CC..."},
    },
}


def shadows(rows: dict[int, str], pal: dict = None) -> str:
    pal = pal or PALETTE
    out = []
    for y, row in sorted(rows.items()):
        for x, ch in enumerate(row):
            if ch in pal:
                # a hair of spread closes antialiasing seams when scaled
                out.append(f"{x * PX}px {y * PX}px 0 0.35px {pal[ch]}")
    return ", ".join(out) or "none"


def body(legs: str) -> str:
    rows = {5 + i: r for i, r in enumerate(BODY)}
    rows[11] = legs
    return shadows(rows)


def hat(rows: list[str]) -> str:
    return shadows({i: r for i, r in enumerate(rows)})


css = [__doc__.replace('"""', "").strip().join(["/* ", " */"]), f"""
.cl-w {{ position: relative; flex: none; display: inline-block; width: {W * PX}px; height: {H * PX}px; }}
.cl-b {{ position: absolute; inset: 0; }}
.cl-b > span {{ position: absolute; left: 0; top: 0; width: {PX}px; height: {PX}px; }}
.cl {{ box-shadow: {body(LEGS_A)}; }}
.cl-eyes {{ box-shadow: {shadows(EYES_OPEN)}; }}
.cl-w.sm {{ transform: scale(0.62); transform-origin: top left; margin: 0 -{round(W * PX * 0.38)}px -{round(H * PX * 0.38)}px 0; }}
.cl-w.lg {{ transform: scale(1.5); transform-origin: top left; margin: 0 {W * PX // 2}px {H * PX // 2}px 0; }}
"""]
for name, rows in HATS.items():
    css.append(f".hat-{name} {{ box-shadow: {hat(rows)}; }}")

css.append(f"""
/* working: walk, bob, dart the eyes, sparkle */
@keyframes cl-walk {{ 0% {{ box-shadow: {body(LEGS_A)}; }} 50% {{ box-shadow: {body(LEGS_B)}; }} }}
@keyframes cl-bob {{ 0%, 100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-{PX}px); }} }}
@keyframes cl-look {{ 0%, 40% {{ transform: translateX(0); }} 50%, 70% {{ transform: translateX({PX}px); }} 80%, 100% {{ transform: translateX(-{PX}px); }} }}
@keyframes cl-spark {{ 0% {{ opacity: 0; transform: translate(0, 0) scale(0.6); }} 30% {{ opacity: 1; }} 100% {{ opacity: 0; transform: translate(6px, -14px) scale(1); }} }}
@keyframes cl-prop {{ 0% {{ box-shadow: {hat(HATS['propeller'])}; }} 50% {{ box-shadow: {hat([PROPELLER_SPIN] + HATS['propeller'][1:])}; }} }}
.cl-w.st-work .cl-b {{ animation: cl-bob 0.5s steps(1) infinite; }}
.cl-w.st-work .cl {{ animation: cl-walk 0.5s steps(1) infinite; }}
.cl-w.st-work .cl-eyes {{ animation: cl-look 2.4s steps(1) infinite; }}
.cl-w.st-work .hat-propeller {{ animation: cl-prop 0.2s steps(1) infinite; }}
.cl-w.st-work .cl-b::after {{ content: '✦'; position: absolute; right: -6px; top: 2px; font: 10px/1 var(--sans); color: #facc15; animation: cl-spark 1.1s ease-out infinite; }}

/* idle: breathe and blink */
@keyframes cl-blink {{ 0%, 92%, 100% {{ box-shadow: {shadows(EYES_OPEN)}; }} 94%, 98% {{ box-shadow: {shadows(EYES_BLINK)}; }} }}
@keyframes cl-breathe {{ 0%, 100% {{ transform: translateY(0); }} 50% {{ transform: translateY({PX // 3 or 1}px); }} }}
.cl-w.st-idle .cl-eyes {{ animation: cl-blink 4s steps(1) infinite; }}
.cl-w.st-idle .cl-b {{ animation: cl-breathe 3s ease-in-out infinite; }}

/* needs you: shake + bang */
@keyframes cl-shake {{ 0%, 100% {{ transform: translateX(0); }} 25% {{ transform: translateX(-2px); }} 75% {{ transform: translateX(2px); }} }}
.cl-w.st-alert .cl-b {{ animation: cl-shake 0.35s steps(2) infinite; }}
.cl-w.st-alert .cl-b::after {{ content: '!'; position: absolute; right: -8px; top: -4px; width: 12px; height: 14px; border-radius: 4px; display: grid; place-items: center; font: 800 10px/1 var(--sans); color: #fff; background: var(--bad, #ef4444); }}

/* done: hop, with a star */
@keyframes cl-jump {{ 0%, 45%, 100% {{ transform: translateY(0); }} 15% {{ transform: translateY(-{PX * 3}px); }} 30% {{ transform: translateY(0); }} }}
.cl-w.st-done .cl-b {{ animation: cl-jump 1.4s ease-out infinite; }}
.cl-w.st-done .cl-b::after {{ content: '★'; position: absolute; right: -6px; top: -2px; font: 10px/1 var(--sans); color: #facc15; animation: cl-spark 1.4s ease-out infinite; }}

/* asleep: shut eyes, drifting z */
@keyframes cl-z {{ 0% {{ opacity: 0; transform: translate(0, 0); }} 40% {{ opacity: 0.9; }} 100% {{ opacity: 0; transform: translate(8px, -12px); }} }}
.cl-w.st-sleep .cl-eyes {{ box-shadow: {shadows(EYES_SHUT)}; }}
.cl-w.st-sleep {{ opacity: 0.78; }}
.cl-w.st-sleep .cl-b::after {{ content: 'z'; position: absolute; right: -4px; top: 0; font: 700 9px/1 var(--mono); color: var(--t3); animation: cl-z 2.6s ease-out infinite; }}
""")
css.append("/* other agents: their own characters (no hats), five variants each, same animations */")
for agent, spec in OTHERS.items():
    key = agent.replace("-", "")
    rows = {i: r for i, r in enumerate(spec["body"])}
    walk_a, walk_b = dict(rows), dict(rows)
    walk_a[11], walk_b[11] = spec["legs"]
    eyes, blink, shut = spec["eyes"], spec.get("blink", {}), spec.get("shut", spec["eyes"])
    base = f".cl-w.ag-{key}"
    # eyes/blink/shut only change with the palette for agents whose eyes use variant colours
    def eye_rules(sel, k, pal):
        css.append(f"{sel} .cl-eyes {{ box-shadow: {shadows(eyes, pal)}; }}")
        css.append(f"@keyframes cl-blink-{k} {{ 0%, 92%, 100% {{ box-shadow: {shadows(eyes, pal)}; }} 94%, 98% {{ box-shadow: {shadows(blink, pal)}; }} }}")
        css.append(f"{sel}.st-idle .cl-eyes {{ animation: cl-blink-{k} {spec.get('blink_s', 4)}s steps(1) infinite; }}")
        css.append(f"{sel}.st-sleep .cl-eyes {{ box-shadow: {shadows(shut, pal)}; }}")
    eye_rules(base, key, PALETTE)
    css.append(f"{base} .cl-hat {{ display: none; }}")
    for i, (name, over, acc) in enumerate(VARIANTS.get(agent, VARIANTS["robot"])):
        pal = dict(PALETTE, **over)
        sel = f"{base}.v{i}"
        k = f"{key}-v{i}"
        css.append(f"/* {agent} · {name} */")
        css.append(f"{sel} .cl {{ box-shadow: {shadows(walk_a, pal)}; }}")
        # the resting pose is the element's own shadow, so the walk only adds the other step
        css.append(f"@keyframes cl-walk-{k} {{ 50% {{ box-shadow: {shadows(walk_b, pal)}; }} }}")
        css.append(f"{sel}.st-work .cl {{ animation: cl-walk-{k} 0.5s steps(1) infinite; }}")
        if acc:
            css.append(f"{sel} .cl-hat {{ display: block; box-shadow: {shadows(ACCESSORIES[acc], pal)}; }}")
        if shadows(eyes, pal) != shadows(eyes, PALETTE):
            eye_rules(sel, k, pal)
print("\n".join(css))
