"""Renders the Agent Deck crew as shareable animated GIFs.

Reads the same pixel grids sprites.py turns into CSS, replays each state's
animation frame by frame (walk, bob, eye darts, sparkles, blink, alert shake,
sleeping z) and pipes raw RGB frames to ffmpeg, which writes a looping GIF
with an exact palette (no dithering, so pixels stay crisp). Stdlib + ffmpeg.

Run: python3 tools/gifs.py [OUT_DIR]   (default ~/Desktop/agent-deck-crew)
"""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "sprites.py")).read()
SP = {}
exec(src[: src.index("css = [")], SP)  # the grids, palette, variants; not the CSS
PAL, BODY, LEGS_A, LEGS_B = SP["PALETTE"], SP["BODY"], SP["LEGS_A"], SP["LEGS_B"]
EYES_OPEN, EYES_BLINK, EYES_SHUT = SP["EYES_OPEN"], SP["EYES_BLINK"], SP["EYES_SHUT"]
HATS, OTHERS, VARIANTS, ACCESSORIES = SP["HATS"], SP["OTHERS"], SP["VARIANTS"], SP["ACCESSORIES"]
PROPELLER_SPIN = SP["PROPELLER_SPIN"]

OUT = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/Desktop/agent-deck-crew")
BG = (20, 19, 27)
CARD = (27, 26, 36)
LABEL = (190, 186, 205)
DIM = (110, 106, 128)
FPS = 12.5
LOOP = 2.4  # seconds; every state's cycle fits it
FRAMES = int(LOOP * FPS)

# --- a 3x5 pixel font for labels ------------------------------------------------
FONT = {
    "A": ["111", "101", "111", "101", "101"], "B": ["110", "101", "110", "101", "110"], "C": ["111", "100", "100", "100", "111"],
    "D": ["110", "101", "101", "101", "110"], "E": ["111", "100", "110", "100", "111"], "F": ["111", "100", "110", "100", "100"],
    "G": ["111", "100", "101", "101", "111"], "H": ["101", "101", "111", "101", "101"], "I": ["111", "010", "010", "010", "111"],
    "J": ["001", "001", "001", "101", "111"], "K": ["101", "101", "110", "101", "101"], "L": ["100", "100", "100", "100", "111"],
    "M": ["101", "111", "111", "101", "101"], "N": ["110", "101", "101", "101", "101"], "O": ["111", "101", "101", "101", "111"],
    "P": ["111", "101", "111", "100", "100"], "Q": ["111", "101", "101", "111", "001"], "R": ["110", "101", "110", "101", "101"],
    "S": ["111", "100", "111", "001", "111"], "T": ["111", "010", "010", "010", "010"], "U": ["101", "101", "101", "101", "111"],
    "V": ["101", "101", "101", "101", "010"], "W": ["101", "101", "111", "111", "101"], "X": ["101", "101", "010", "101", "101"],
    "Y": ["101", "101", "010", "010", "010"], "Z": ["111", "001", "010", "100", "111"], "0": ["111", "101", "101", "101", "111"],
    "1": ["010", "110", "010", "010", "111"], "2": ["111", "001", "111", "100", "111"], "3": ["111", "001", "011", "001", "111"],
    "4": ["101", "101", "111", "001", "001"], "5": ["111", "100", "111", "001", "111"], "6": ["111", "100", "111", "101", "111"],
    "7": ["111", "001", "001", "010", "010"], "8": ["111", "101", "111", "101", "111"], "9": ["111", "101", "111", "001", "111"],
    " ": ["000", "000", "000", "000", "000"], "-": ["000", "000", "111", "000", "000"], "!": ["010", "010", "010", "000", "010"],
    ".": ["000", "000", "000", "000", "010"], "'": ["010", "010", "000", "000", "000"], "·": ["000", "000", "010", "000", "000"],
}


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def mix(c, bg, a):
    return tuple(round(c[i] * a + bg[i] * (1 - a)) for i in range(3))


class Canvas:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.buf = bytearray(bytes(BG) * (w * h))

    def rect(self, x, y, w, h, rgb):
        x0, y0, x1, y1 = max(0, int(x)), max(0, int(y)), min(self.w, int(x + w)), min(self.h, int(y + h))
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(rgb) * (x1 - x0)
        for yy in range(y0, y1):
            i = (yy * self.w + x0) * 3
            self.buf[i : i + len(row)] = row

    def text(self, s, x, y, scale, rgb, center=False):
        s = s.upper().replace("É", "E")
        if center:
            x -= (len(s) * 4 - 1) * scale / 2
        for ch in s:
            g = FONT.get(ch, FONT[" "])
            for gy, line in enumerate(g):
                for gx, bit in enumerate(line):
                    if bit == "1":
                        self.rect(x + gx * scale, y + gy * scale, scale, scale, rgb)
            x += 4 * scale


def grid(cv, rows, pal, ox, oy, s, alpha=1.0, bg=CARD):
    for y, line in rows.items():
        for x, ch in enumerate(line):
            if ch in pal:
                rgb = hexrgb(pal[ch])
                cv.rect(ox + x * s, oy + y * s, s, s, mix(rgb, bg, alpha) if alpha < 1 else rgb)


def phase(t, period):
    return (t % period) / period


def look(t):
    """Eye darts, as cl-look: 0 → right → left over 2.4 s."""
    p = phase(t, 2.4)
    return 0 if p < 0.5 else (1 if p < 0.8 else -1)


def sparkle(cv, ox, oy, s, t, glyph_rgb=(250, 204, 21), bg=CARD):
    """✦ rising to the upper right and fading, as cl-spark (1.1 s)."""
    p = phase(t, 1.1)
    a = min(1, p / 0.3) if p < 0.3 else max(0, 1 - (p - 0.3) / 0.7)
    x = ox + 12 * s + p * 2 * s
    y = oy + 1 * s - p * 4.5 * s
    c = mix(glyph_rgb, bg, a)
    u = max(1, s // 2)
    cv.rect(x + u, y, u, 3 * u, c)
    cv.rect(x, y + u, 3 * u, u, c)


def draw(cv, kind, look_id, state, ox, oy, s, t):
    """One character at (ox, oy), sprite pixels of size s, at time t."""
    bob = shake = 0
    alpha = 0.78 if state == "sleep" else 1.0
    if state == "work":
        bob = -1 if phase(t, 0.5) >= 0.5 else 0
    elif state == "alert":
        shake = -1 if phase(t, 0.35) < 0.5 else 1
    x0, y0 = ox + shake * max(1, s // 2), oy + bob * s
    walk = state == "work" and phase(t, 0.5) >= 0.5

    if kind == "claude":
        pal = PAL
        rows = {5 + i: r for i, r in enumerate(BODY)}
        rows[11] = LEGS_B if walk else LEGS_A
        grid(cv, rows, pal, x0, y0, s, alpha)
        if state == "sleep":
            eyes = EYES_SHUT
        elif state == "idle" and phase(t, 2.4) > 0.9:
            eyes = EYES_BLINK
        else:
            eyes = EYES_OPEN
        dx = look(t) * s if state == "work" else 0
        grid(cv, eyes, pal, x0 + dx, y0, s, alpha)
        hat = HATS[look_id]
        if look_id == "propeller" and state == "work" and phase(t, 0.2) >= 0.5:
            hat = [PROPELLER_SPIN] + hat[1:]
        grid(cv, {i: r for i, r in enumerate(hat)}, pal, x0, y0, s, alpha)
    else:
        spec = OTHERS[kind]
        name, over, acc = VARIANTS.get(kind, VARIANTS["robot"])[look_id]
        pal = dict(PAL, **over)
        rows = {i: r for i, r in enumerate(spec["body"])}
        rows[11] = spec["legs"][1 if walk else 0]
        grid(cv, rows, pal, x0, y0, s, alpha)
        if state == "sleep":
            eyes = spec.get("shut", spec["eyes"])
        elif state == "idle" and phase(t, spec.get("blink_s", 2.4)) > 0.85:
            eyes = spec.get("blink", {})
        else:
            eyes = spec["eyes"]
        dx = look(t) * s if state == "work" else 0
        grid(cv, eyes, pal, x0 + dx, y0, s, alpha)
        if acc:
            grid(cv, ACCESSORIES[acc], pal, x0, y0, s, alpha)

    if state == "work":
        sparkle(cv, x0, y0, s, t)
    elif state == "alert":
        bx, by = x0 + 11 * s, y0 - 1 * s
        cv.rect(bx, by, 4 * s, 5 * s, (239, 68, 68))
        cv.text("!", bx + 0.5 * s, by + 0.5 * s, max(1, s * 4 // 5), (255, 255, 255))
    elif state == "sleep":
        p = phase(t, 2.6)
        a = min(1, p / 0.4) if p < 0.4 else max(0, 1 - (p - 0.4) / 0.6)
        cv.text("z", x0 + 12 * s + p * 3 * s, y0 + 1 * s - p * 4 * s, max(1, s // 2), mix(LABEL, CARD, a * 0.9))


def write_gif(path, w, h, render):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(FPS), "-i", "-",
         "-vf", "split[a][b];[a]palettegen=max_colors=255:stats_mode=full[p];[b][p]paletteuse=dither=none", "-loop", "0", path],
        stdin=subprocess.PIPE)
    for f in range(FRAMES):
        cv = Canvas(w, h)
        render(cv, f / FPS)
        ff.stdin.write(cv.buf)
    ff.stdin.close()
    ff.wait()
    print(f"wrote {path}  ({w}x{h}, {FRAMES} frames, {os.path.getsize(path) // 1024} KB)")


# --- the sheets --------------------------------------------------------------------
STATES = [("work", "working"), ("idle", "idle"), ("alert", "needs you"), ("sleep", "asleep")]
CAST = [("claude", "wizard", "Claude"), ("codex", 0, "Codex"), ("gemini", 0, "Gemini"), ("copilot", 0, "Copilot"),
        ("cursor-agent", 0, "Cursor"), ("opencode", 0, "opencode"), ("robot", 0, "Other agents")]


def cell(cv, x, y, w, h):
    cv.rect(x, y, w, h, CARD)


def sheet(path, items, cols, s=6, cw=150, ch=150, title=None):
    """items: (kind, look, state, label). A grid of cards, each a character with its label."""
    rows = (len(items) + cols - 1) // cols
    top = 46 if title else 16
    w, h = 16 + cols * (cw + 12) + 4, top + rows * (ch + 12) + 8

    def render(cv, t):
        if title:
            cv.text(title, 20, 16, 3, LABEL)
        for i, (kind, look_id, state, label) in enumerate(items):
            cx, cy = 16 + (i % cols) * (cw + 12), top + (i // cols) * (ch + 12)
            cell(cv, cx, cy, cw, ch)
            draw(cv, kind, look_id, state, cx + (cw - 12 * s) // 2, cy + 22, s, t)
            cv.text(label, cx + cw / 2, cy + ch - 22, 2, LABEL, center=True)

    write_gif(path, w, h, render)


def matrix(path, s=6):
    """Agents down, states across: the whole story in one GIF."""
    lw, cw, ch = 150, 140, 120
    w, h = 16 + lw + 4 * (cw + 10) + 6, 60 + len(CAST) * (ch + 10) + 6

    def render(cv, t):
        cv.text("AGENT DECK CREW", 20, 16, 3, LABEL)
        for j, (_, lbl) in enumerate(STATES):
            cv.text(lbl, 16 + lw + j * (cw + 10) + cw / 2, 44, 2, DIM, center=True)
        for i, (kind, look_id, name) in enumerate(CAST):
            y = 60 + i * (ch + 10)
            cv.text(name, 20, y + ch / 2 - 5, 2, LABEL)
            for j, (state, _) in enumerate(STATES):
                x = 16 + lw + j * (cw + 10)
                cell(cv, x, y, cw, ch)
                draw(cv, kind, look_id, state, x + (cw - 12 * s) // 2, y + 26, s, t)

    write_gif(path, w, h, render)


if __name__ == "__main__":
    matrix(os.path.join(OUT, "crew-all-states.gif"))
    for state, label in STATES:
        sheet(os.path.join(OUT, f"state-{label.replace(' ', '-')}.gif"),
              [(k, l, state, n) for k, l, n in CAST], cols=7, title=label)
    sheet(os.path.join(OUT, "claude-hats.gif"),
          [("claude", h, "work", n) for h, n in [("wizard", "Merlin"), ("party", "Confetti"), ("tophat", "Sir Tokens"),
           ("crown", "Queen Context"), ("propeller", "Zippy"), ("chef", "Chef Prompt"), ("cowboy", "Tex"),
           ("viking", "Bjorn"), ("cap", "Coach"), ("beanie", "Pom")]], cols=5, title="claude · 10 hats")
    for kind, _, label in CAST[1:]:
        names = VARIANTS.get(kind, VARIANTS["robot"])
        sheet(os.path.join(OUT, f"variants-{label.split()[0].lower()}.gif"),
              [(kind, i, "work", v[0]) for i, v in enumerate(names)], cols=5, title=f"{label} · 5 variants")
