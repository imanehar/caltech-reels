"""Groupe Caltech branded Reel renderer.
Usage: python3 reel.py spec.json out.mp4   (or: python3 reel.py spec.json --stills outdir)
A spec is a list of scenes; each scene type knows its timing, drawing and sound cues."""
import json, math, os, subprocess, sys, tempfile, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, FPS = 1080, 1920, 30
INK, INK2, PAPER, PAPER2 = (22, 22, 25), (34, 34, 39), (242, 241, 236), (228, 226, 219)
GRAY, GRAY_D, COBALT, COBALT_L = (138, 140, 145), (92, 94, 100), (42, 63, 181), (120, 138, 235)
GREEN = (46, 160, 105)

_fc = {}
def F(kind, size):
    name = {"serif": "newsreader-latin-500-normal", "serif_r": "newsreader-latin-400-normal", "serif_b": "newsreader-latin-600-normal",
            "serif_i": "newsreader-latin-400-italic", "sans": "instrument-sans-latin-400-normal", "sans_m": "instrument-sans-latin-500-normal",
            "sans_sb": "instrument-sans-latin-600-normal", "sans_b": "instrument-sans-latin-700-normal"}[kind]
    k = (name, size)
    if k not in _fc: _fc[k] = ImageFont.truetype(os.path.join(HERE, "fonts", name + ".woff"), size)
    return _fc[k]

def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def ease(x): x = clamp(x); return 1 - (1 - x) ** 3
def back(x): x = clamp(x); c = 1.70158; return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2
def prog(t, s, d=0.5): return ease((t - s) / d)
def mix(c, bg, a): return tuple(int(bg[i] + (c[i] - bg[i]) * a) for i in range(3))

_logo = Image.open(os.path.join(HERE, "logo.png")).convert("RGBA")
def logo(size): return _logo.resize((size, size), Image.LANCZOS)

_bgc = {}
def bg(dark):
    if dark not in _bgc:
        base = Image.new("RGB", (W, H), INK if dark else PAPER)
        if dark:
            glow = Image.new("RGB", (W, H), (0, 0, 0))
            ImageDraw.Draw(glow).ellipse([W * 0.35, -H * 0.15, W * 1.35, H * 0.35], fill=(30, 40, 110))
            glow = glow.filter(ImageFilter.GaussianBlur(260))
            base = Image.fromarray(np.clip(np.asarray(base, "int16") + np.asarray(glow, "int16") // 2, 0, 255).astype("uint8"))
        else:
            d = ImageDraw.Draw(base)
            for x in range(90, W, 180): d.line([(x, 0), (x, H)], fill=(233, 232, 226), width=1)
        _bgc[dark] = base
    return _bgc[dark].copy()

def wrap(d, s, f, maxw):
    out = []
    for para in str(s).split("\n"):
        cur = ""
        for w in para.split():
            t = (cur + " " + w).strip()
            if d.textlength(t, font=f) <= maxw: cur = t
            else: out.append(cur); cur = w
        out.append(cur)
    return out

def text_c(d, y, s, f, col, bgc, a=1.0, dy=0.0):
    if a <= 0: return
    w = d.textlength(s, font=f); d.text(((W - w) / 2, y + dy), s, font=f, fill=mix(col, bgc, a))

def chrome(img, dark):
    """Brand frame: logo + wordmark top-left, AI disclosure top-right."""
    d = ImageDraw.Draw(img)
    img.paste(logo(64), (72, 78), logo(64))
    fg = PAPER if dark else INK
    d.text((152, 86), "Groupe Caltech", font=F("serif", 38), fill=fg)
    s = "Contenu généré par IA"
    f = F("sans_m", 24); w = d.textlength(s, font=f)
    d.rounded_rectangle([W - 72 - w - 36, 88, W - 72, 132], 22, outline=GRAY_D if dark else (200, 198, 190), width=2)
    d.text((W - 72 - w - 18, 96), s, font=f, fill=GRAY if dark else GRAY_D)
    d.line([(72, 172), (W - 72, 172)], fill=(48, 48, 54) if dark else (214, 212, 204), width=2)
    return d

def kicker(d, y, s, col, a, bgc, center=True):
    if a <= 0: return
    f = F("sans_sb", 30); s = s.upper()
    sp = " ".join(s)  # letter-spaced label
    w = d.textlength(sp, font=f); x = (W - w) / 2 if center else 96
    d.text((x, y), sp, font=f, fill=mix(col, bgc, a))

# ---------------- scene types ----------------
class Scene:
    dark = True
    def __init__(self, s): self.s = s
    def cues(self): return []

class Hook(Scene):
    """Big serif headline, line by line, optional italic sub and pill."""
    def __init__(self, s):
        super().__init__(s); self.dark = s.get("dark", True)
        self.dur = 1.0 + 0.75 * len(s["lines"]) + (0.8 if s.get("sub") else 0) + (0.9 if s.get("pill") else 0) + 0.6
    def cues(self):
        c = [0.15 + i * 0.75 for i in range(len(self.s["lines"]))]
        if self.s.get("pill"): c.append(0.15 + 0.75 * len(self.s["lines"]) + (0.8 if self.s.get("sub") else 0))
        return [("pop", x) for x in c]
    def draw(self, t):
        img = bg(self.dark); d = chrome(img, self.dark); bgc = INK if self.dark else PAPER; fg = PAPER if self.dark else INK
        lines = self.s["lines"]; f = F("serif", 118 if max(len(l) for l in lines) < 16 else 96)
        lh = int(f.size * 1.12); y0 = 760 - lh * len(lines) / 2
        if self.s.get("kicker"): kicker(d, y0 - 110, self.s["kicker"], COBALT_L if self.dark else COBALT, prog(t, 0.05), bgc)
        for i, l in enumerate(lines):
            a = prog(t, 0.15 + i * 0.75, 0.55)
            col = (COBALT_L if self.dark else COBALT) if i == self.s.get("accent_line", -1) else fg
            text_c(d, y0 + i * lh, l, F("serif_i", f.size) if i == self.s.get("accent_line", -1) else f, col, bgc, a, (1 - a) * 40)
        t2 = 0.15 + 0.75 * len(lines)
        y = y0 + lh * len(lines) + 60
        if self.s.get("sub"):
            a = prog(t, t2, 0.5)
            for j, l in enumerate(wrap(d, self.s["sub"], F("sans", 46), 860)):
                text_c(d, y + j * 62, l, F("sans", 46), GRAY if self.dark else GRAY_D, bgc, a, (1 - a) * 25)
            y += 62 * len(wrap(d, self.s["sub"], F("sans", 46), 860)) + 70; t2 += 0.8
        if self.s.get("pill"):
            a = prog(t, t2, 0.5); f2 = F("sans_sb", 40); s = self.s["pill"] + "  ↓"
            w = d.textlength(s, font=f2); yy = y + 40 + (1 - a) * 30
            if a > 0:
                d.rounded_rectangle([(W - w) / 2 - 44, yy, (W + w) / 2 + 44, yy + 92], 46, fill=mix(COBALT, bgc, a))
                d.text(((W - w) / 2, yy + 22), s, font=f2, fill=mix(PAPER, bgc, a))
        return img

PX0, PY0, PX1, PY1 = 150, 300, 930, 1640
def phone(img, title, sub, initials, screen=(16, 16, 19), header=True):
    L = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(L)
    d.rounded_rectangle([PX0 - 14, PY0 - 14, PX1 + 14, PY1 + 14], 82, fill=(52, 52, 58, 255))
    d.rounded_rectangle([PX0, PY0, PX1, PY1], 70, fill=screen + (255,))
    d.rounded_rectangle([(PX0 + PX1) / 2 - 90, PY0 + 20, (PX0 + PX1) / 2 + 90, PY0 + 54], 17, fill=(0, 0, 0, 255))
    if header:
        d.line([(PX0, PY0 + 190), (PX1, PY0 + 190)], fill=(44, 44, 50, 255), width=2)
        d.ellipse([PX0 + 40, PY0 + 90, PX0 + 120, PY0 + 170], fill=COBALT + (255,))
        f = F("sans_b", 32); w = d.textlength(initials, font=f)
        d.text((PX0 + 80 - w / 2, PY0 + 110), initials, font=f, fill=PAPER + (255,))
        d.text((PX0 + 145, PY0 + 92), title, font=F("sans_sb", 38), fill=PAPER + (255,))
        d.ellipse([PX0 + 147, PY0 + 153, PX0 + 161, PY0 + 167], fill=GREEN + (255,))
        d.text((PX0 + 172, PY0 + 141), sub, font=F("sans", 28), fill=GRAY + (255,))
    img.paste(L, (0, 0), L)

class Notif(Scene):
    """Lock screen with an incoming request notification + caption below."""
    dur = 4.2
    def cues(self): return [("ding", 1.0)] + ([("pop", 2.5)] if self.s.get("caption") else [])
    def draw(self, t):
        img = bg(True); chrome(img, True)
        L = Image.new("RGB", (W, H), INK); off = int((1 - ease(t / 0.6)) * 900)
        tmp = bg(True); chrome(tmp, True)
        phone(tmp, "", "", "", screen=(20, 20, 26), header=False)
        d = ImageDraw.Draw(tmp)
        f = F("serif", 160); s = self.s.get("time", "21:14"); w = d.textlength(s, font=f)
        d.text(((W - w) / 2, PY0 + 150), s, font=f, fill=PAPER)
        s2 = self.s.get("date", "mardi"); f2 = F("sans", 36); w2 = d.textlength(s2, font=f2)
        d.text(((W - w2) / 2, PY0 + 350), s2, font=f2, fill=GRAY)
        img.paste(tmp.crop((0, 180, W, H)).crop((0, 0, W, H - 180 - max(0, off - 0))), (0, 180 + off))
        img2 = bg(True); chrome(img2, True); img2.paste(img.crop((0, 180, W, H)), (0, 180)); img = img2
        d = ImageDraw.Draw(img)
        p = prog(t, 1.0, 0.5)
        if p > 0:
            a = clamp(p * 2); y = PY0 + 500 + (1 - back(p)) * -60
            d.rounded_rectangle([PX0 + 30, y, PX1 - 30, y + 300], 36, fill=mix((48, 48, 56), (20, 20, 26), a))
            d.rounded_rectangle([PX0 + 60, y + 32, PX0 + 108, y + 80], 12, fill=mix(COBALT, (20, 20, 26), a))
            d.text((PX0 + 130, y + 38), self.s.get("label", "NOUVELLE DEMANDE").upper(), font=F("sans_sb", 26), fill=mix(GRAY, (20, 20, 26), a))
            d.text((PX1 - 200, y + 38), "maintenant", font=F("sans", 26), fill=mix(GRAY, (20, 20, 26), a))
            d.text((PX0 + 60, y + 104), self.s["title"], font=F("sans_b", 42), fill=mix(PAPER, (20, 20, 26), a))
            for i, l in enumerate(self.s.get("lines", [])[:2]):
                d.text((PX0 + 60, y + 166 + i * 50), l, font=F("sans_m", 34), fill=mix((205, 205, 212), (20, 20, 26), a))
        p2 = prog(t, 2.5, 0.5)
        if p2 > 0 and self.s.get("caption"):
            text_c(d, 1700, self.s["caption"], F("serif_i", 54), COBALT_L, INK, p2, (1 - p2) * 20)
        return img

class Chat(Scene):
    """Messaging thread: AI (cobalt, left) vs client (grey, right); optional photo row and badge."""
    def __init__(self, s):
        super().__init__(s); self.times = []; t = 0.9
        for m in s["messages"]:
            if m["side"] == "ai": t += 0.55
            self.times.append(t); t += 1.0 + 0.012 * len(m.get("text", ""))
        self.dur = t + 0.9
    def cues(self):
        c = [("pop", x) for x in self.times]
        if self.s.get("badge"): c.append(("ding", 1.2))
        return c
    def draw(self, t):
        img = bg(True); chrome(img, True)
        phone(img, self.s.get("business", "Entreprise"), self.s.get("status", "Assistant IA · en ligne"), self.s.get("initials", "AI"))
        d = ImageDraw.Draw(img); f = F("sans_m", 34)
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0)); dc = ImageDraw.Draw(layer)
        items = []
        for m in self.s["messages"]:
            h = 210 if m.get("photos") else 46 * len(wrap(d, m["text"], f, 520)) + 40
            items.append((m, h))
        shown = sum(h + 22 for (m, h), ts in zip(items, self.times) if t >= ts)
        scroll = max(0, shown - (PY1 - 60 - (PY0 + 230)))
        yy = PY0 + 230 - scroll
        for (m, h), ts in zip(items, self.times):
            p = prog(t, ts, 0.4); dy = (1 - ease(p)) * 40; a = clamp(p * 2)
            if m["side"] == "ai" and ts - 0.55 <= t < ts:
                x0 = PX0 + 40; dc.rounded_rectangle([x0, yy, x0 + 130, yy + 70], 30, fill=(40, 52, 120, 255))
                for i in range(3):
                    k = (math.sin(t * 9 - i * 0.9) + 1) / 2
                    dc.ellipse([x0 + 30 + i * 28, yy + 28 - k * 8, x0 + 46 + i * 28, yy + 44 - k * 8], fill=(210, 218, 255, 255))
            if p > 0:
                if m.get("photos"):
                    for k in range(m["photos"]):
                        x0 = PX1 - 40 - 3 * 190 + k * 190 + 10
                        col = [(120, 128, 140), (150, 138, 120), (112, 126, 120)][k % 3]
                        dc.rounded_rectangle([x0, yy + dy, x0 + 170, yy + 200 + dy], 22, fill=col + (int(255 * a),))
                        dc.rectangle([x0 + 45, yy + 65 + dy, x0 + 125, yy + 135 + dy], outline=(235, 235, 238, int(255 * a)), width=4)
                else:
                    lines = wrap(d, m["text"], f, 520); bw = max(d.textlength(l, font=f) for l in lines) + 56
                    x0 = PX0 + 40 if m["side"] == "ai" else PX1 - 40 - bw
                    fill = COBALT if m["side"] == "ai" else (52, 52, 60)
                    dc.rounded_rectangle([x0, yy + dy, x0 + bw, yy + dy + h], 30, fill=fill + (int(255 * a),))
                    for i, l in enumerate(lines):
                        dc.text((x0 + 28, yy + dy + 20 + i * 46), l, font=f, fill=PAPER + (int(255 * a),))
            yy += h + 22
        mask = Image.new("L", (W, H), 0); ImageDraw.Draw(mask).rectangle([PX0, PY0 + 195, PX1, PY1 - 30], fill=255)
        img.paste(layer, (0, 0), Image.fromarray(np.minimum(np.asarray(layer.split()[3]), np.asarray(mask))))
        if self.s.get("badge"):
            p = prog(t, 1.2, 0.45)
            if p > 0:
                f2 = F("sans_b", 38); s = self.s["badge"]; w = d.textlength(s, font=f2); yb = 196 + (1 - back(p)) * -30
                d.rounded_rectangle([(W - w) / 2 - 36, yb, (W + w) / 2 + 36, yb + 76], 38, fill=mix(PAPER, INK, p))
                d.text(((W - w) / 2, yb + 16), s, font=f2, fill=mix(INK, INK, 1) if p > 0.5 else mix(PAPER, INK, p))
        return img

class Card(Scene):
    """Paper editorial card: title + key/value rows, optional confirmation strip."""
    dark = False
    def __init__(self, s):
        super().__init__(s); self.dur = 1.6 + 0.24 * len(s["rows"]) + (1.4 if s.get("confirm") else 0) + 0.9
    def cues(self):
        c = [("tick", 0.9 + i * 0.24) for i in range(len(self.s["rows"]))]
        if self.s.get("confirm"): c.append(("chime", 1.2 + 0.24 * len(self.s["rows"])))
        return c
    def draw(self, t):
        img = bg(False); d = chrome(img, False); bgc = PAPER
        kicker(d, 240, self.s.get("kicker", "Pendant ce temps"), COBALT, prog(t, 0.05), bgc)
        if self.s.get("intro"):
            a = prog(t, 0.1); text_c(d, 300, self.s["intro"], F("serif_i", 54), INK, bgc, a, (1 - a) * 20)
        p = prog(t, 0.35, 0.5); y0 = 430 + (1 - ease(p)) * 60; a = clamp(p * 1.5)
        d.rounded_rectangle([96, y0, W - 96, y0 + 190 + 108 * len(self.s["rows"])], 36, fill=mix((255, 255, 252), bgc, a), outline=mix((214, 212, 204), bgc, a), width=2)
        d.text((150, y0 + 52), self.s["title"], font=F("serif", 58), fill=mix(INK, bgc, a))
        if self.s.get("tag"):
            f = F("sans_sb", 28); w = d.textlength(self.s["tag"], font=f)
            d.rounded_rectangle([W - 150 - w - 40, y0 + 62, W - 150, y0 + 116], 27, fill=mix(COBALT, bgc, a))
            d.text((W - 150 - w - 20, y0 + 72), self.s["tag"], font=f, fill=mix(PAPER, bgc, a))
        for i, (k, v) in enumerate(self.s["rows"]):
            pr = prog(t, 0.9 + i * 0.24, 0.35); yy = y0 + 170 + i * 108
            d.line([(150, yy - 16), (W - 150, yy - 16)], fill=mix((226, 224, 216), bgc, a), width=2)
            d.text((150, yy + 16 + (1 - pr) * 14), k, font=F("sans_m", 36), fill=mix(GRAY_D, (255, 255, 252), pr))
            d.text((450, yy + 12 + (1 - pr) * 14), v, font=F("sans_sb", 40), fill=mix(INK, (255, 255, 252), pr))
        if self.s.get("confirm"):
            tc = 1.2 + 0.24 * len(self.s["rows"]); p2 = prog(t, tc, 0.5)
            if p2 > 0:
                yc = y0 + 230 + 108 * len(self.s["rows"]) + (1 - back(p2)) * 40
                d.rounded_rectangle([96, yc, W - 96, yc + 170], 36, fill=mix(INK, bgc, p2))
                d.ellipse([146, yc + 45, 226, yc + 125], fill=mix(COBALT, INK, p2))
                d.line([(167, yc + 86), (183, yc + 102), (207, yc + 70)], fill=PAPER, width=8)
                d.text((262, yc + 38), self.s["confirm"][0], font=F("sans_b", 40), fill=mix(PAPER, INK, p2))
                d.text((262, yc + 94), self.s["confirm"][1], font=F("sans", 34), fill=mix((190, 192, 200), INK, p2))
        return img

class Statement(Scene):
    """Kicker + serif statement lines, optional message bubble and closing line."""
    def __init__(self, s):
        super().__init__(s); self.dark = s.get("dark", True)
        self.dur = 1.0 + 0.7 * len(s["lines"]) + (1.4 if s.get("bubble") else 0) + (1.0 if s.get("after") else 0) + 0.7
    def cues(self):
        c = [("pop", 0.2 + i * 0.7) for i in range(len(self.s["lines"]))]; t = 0.2 + 0.7 * len(self.s["lines"])
        if self.s.get("bubble"): c.append(("pop", t + 0.3)); t += 1.4
        if self.s.get("after"): c.append(("pop", t))
        return c
    def draw(self, t):
        img = bg(self.dark); d = chrome(img, self.dark); bgc = INK if self.dark else PAPER; fg = PAPER if self.dark else INK
        acc = COBALT_L if self.dark else COBALT
        if self.s.get("kicker"): kicker(d, 430, self.s["kicker"], acc, prog(t, 0.05), bgc)
        f = F("serif", 92); y = 510
        for i, l in enumerate(self.s["lines"]):
            a = prog(t, 0.2 + i * 0.7)
            text_c(d, y, l, F("serif_i", 92) if i == self.s.get("accent_line", -1) else f, acc if i == self.s.get("accent_line", -1) else fg, bgc, a, (1 - a) * 30)
            y += 108
        tt = 0.2 + 0.7 * len(self.s["lines"]); y += 60
        b = self.s.get("bubble")
        if b:
            p = prog(t, tt + 0.3, 0.5)
            if p > 0:
                if b.get("label"):
                    f2 = F("sans_sb", 28); w = d.textlength(b["label"].upper(), font=f2)
                    d.rounded_rectangle([(W - w) / 2 - 26, y, (W + w) / 2 + 26, y + 58], 29, outline=mix(acc, bgc, p), width=2)
                    d.text(((W - w) / 2, y + 12), b["label"].upper(), font=f2, fill=mix(acc, bgc, p)); y += 100
                fb = F("sans_m", 42); lines = wrap(d, b["text"], fb, 700); bh = 60 * len(lines) + 56; yy = y + (1 - ease(p)) * 40
                d.rounded_rectangle([150, yy, W - 150, yy + bh], 40, fill=mix(COBALT, bgc, p))
                for i, l in enumerate(lines): d.text((190, yy + 28 + i * 60), l, font=fb, fill=mix(PAPER, bgc, p))
                y += bh + 80
            else: y += 260
            tt += 1.4
        if self.s.get("after"):
            a = prog(t, tt); text_c(d, y, self.s["after"], F("serif_i", 60), acc, bgc, a, (1 - a) * 20)
        return img

class ListScene(Scene):
    """Numbered list (e.g. '3 tâches à automatiser')."""
    def __init__(self, s): super().__init__(s); self.dark = s.get("dark", False); self.dur = 1.6 + 1.1 * len(s["items"]) + 0.8
    def cues(self): return [("pop", 0.1)] + [("tick", 1.0 + i * 1.1) for i in range(len(self.s["items"]))]
    def draw(self, t):
        img = bg(self.dark); d = chrome(img, self.dark); bgc = INK if self.dark else PAPER; fg = PAPER if self.dark else INK
        a = prog(t, 0.1)
        y = 300
        for l in wrap(d, self.s["title"], F("serif", 80), 900):
            text_c(d, y, l, F("serif", 80), fg, bgc, a, (1 - a) * 25); y += 92
        y += 70
        for i, it in enumerate(self.s["items"]):
            p = prog(t, 1.0 + i * 1.1, 0.5); dy = (1 - ease(p)) * 30
            if p <= 0: continue
            d.text((110, y + dy), f"0{i+1}", font=F("serif_i", 88), fill=mix(COBALT_L if self.dark else COBALT, bgc, p))
            ty = y + 14 + dy
            for j, l in enumerate(wrap(d, it[0], F("sans_b", 46), 700)):
                d.text((270, ty), l, font=F("sans_b", 46), fill=mix(fg, bgc, p)); ty += 58
            for l in wrap(d, it[1], F("sans", 36), 700):
                d.text((270, ty + 4), l, font=F("sans", 36), fill=mix(GRAY if self.dark else GRAY_D, bgc, p)); ty += 48
            y = max(y + 230, ty + 60)
        return img

class CTA(Scene):
    dur = 5.4
    def cues(self): return [("pop", 0.1), ("pop", 0.7), ("chime", 1.4), ("pop", 2.2)]
    def draw(self, t):
        img = bg(True); d = chrome(img, True); bgc = INK
        lines = self.s.get("lines", ["Aucune demande perdue.", "Même à 21 h."])
        for i, l in enumerate(lines[:2]):
            a = prog(t, 0.1 + i * 0.6)
            text_c(d, 420 + i * 108, l, F("serif_i", 78) if i == 1 else F("serif", 78), COBALT_L if i == 1 else PAPER, bgc, a, (1 - a) * 30)
        p = prog(t, 1.4, 0.5)
        if p > 0:
            s = "Commente " + self.s.get("keyword", "AUDIT"); f = F("sans_b", 74); w = d.textlength(s, font=f)
            k = back(p) * (1 + 0.02 * math.sin(max(0, t - 2) * 5)); cx, cy = W / 2, 840
            hw, hh = (w / 2 + 64) * k, 82 * k
            d.rounded_rectangle([cx - hw, cy - hh, cx + hw, cy + hh], int(max(1, hh)), fill=mix(PAPER, bgc, clamp(p * 2)))
            if k > 0.6: d.text((cx - w / 2, cy - 46), s, font=f, fill=INK)
        a = prog(t, 2.2)
        y = 990
        for l in wrap(d, self.s.get("sub", "et on t'envoie 3 tâches que ton entreprise peut automatiser."), F("sans", 46), 820):
            text_c(d, y, l, F("sans", 46), (210, 210, 216), bgc, a, (1 - a) * 20); y += 62
        text_c(d, y + 6, self.s.get("free", "Gratuit."), F("serif_i", 54), COBALT_L, bgc, a, (1 - a) * 20)
        a2 = prog(t, 2.9)
        if a2 > 0:
            lg = logo(120); img.paste(lg, ((W - 120) // 2, 1300), lg)
            text_c(d, 1448, "Groupe Caltech", F("serif", 52), PAPER, bgc, a2)
            text_c(d, 1516, "The systems behind better business.", F("serif_i", 36), GRAY, bgc, a2)
        return img

TYPES = {"hook": Hook, "notif": Notif, "chat": Chat, "card": Card, "statement": Statement, "list": ListScene, "cta": CTA}

# ---------------- audio ----------------
def make_audio(cues, dur, path, seed=0):
    SR = 44100; t = np.arange(int(SR * dur)) / SR; out = np.zeros_like(t)
    note = lambda m: 440 * 2 ** ((m - 69) / 12)
    progs = [[[57, 60, 64], [53, 57, 60], [48, 55, 60], [55, 59, 62]], [[50, 53, 57], [46, 50, 53], [53, 57, 60], [48, 52, 55]],
             [[52, 55, 59], [48, 52, 55], [55, 59, 62], [50, 54, 57]]]
    chords = progs[seed % len(progs)]; bar = 2.4
    for i in range(int(dur / bar) + 1):
        ch = chords[i % 4]; s = i * bar; m = (t >= s) & (t < s + bar + 0.6); tt = t[m] - s
        env = np.minimum(1, tt / 0.4) * np.exp(-np.maximum(0, tt - bar) * 5)
        for n in ch: out[m] += 0.045 * env * (np.sin(2 * np.pi * note(n) * tt) + 0.3 * np.sin(2 * np.pi * 2 * note(n) * tt + 0.5))
        out[m] += 0.07 * env * np.sin(2 * np.pi * note(ch[0] - 12) * tt)
    for k in range(int(dur / 0.6)):
        s = k * 0.6; m = (t >= s) & (t < s + 0.25); tt = t[m] - s
        out[m] += 0.2 * np.sin(2 * np.pi * (50 + 90 * np.exp(-tt * 30)) * tt) * np.exp(-tt * 14)
        s2 = s + 0.3; m = (t >= s2) & (t < s2 + 0.05); tt = t[m] - s2
        out[m] += 0.022 * np.random.default_rng(k).standard_normal(m.sum()) * np.exp(-tt * 90)
    def tone(s, f, v, d, decay, sweep=0.0):
        m = (t >= s) & (t < s + d); tt = t[m] - s
        out[m] += v * np.sin(2 * np.pi * f * (1 + sweep * np.exp(-tt * 40)) * tt) * np.exp(-tt * decay)
    for kind, s in cues:
        if kind == "pop": tone(s, 820, 0.17, 0.12, 35, 0.6)
        elif kind == "tick": tone(s, 1200, 0.09, 0.08, 50, 0.3)
        elif kind == "ding": tone(s, 1318, 0.13, 0.6, 7); tone(s + 0.09, 1760, 0.13, 0.6, 7)
        elif kind == "chime":
            for j, f in enumerate((1046, 1318, 1568)): tone(s + j * 0.09, f, 0.13, 0.6, 7)
    fo = t > dur - 1.2; out[fo] *= (dur - t[fo]) / 1.2
    out = out / (np.max(np.abs(out)) + 1e-9) * 0.85
    pcm = (np.repeat(out[:, None], 2, axis=1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w: w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())

# ---------------- render ----------------
def build(spec):
    return [TYPES[s["type"]](s) for s in spec["scenes"]]

def render(spec, out_path):
    scenes = build(spec); tmpd = tempfile.mkdtemp(); files = []; cues = []; t0 = 0.0
    for idx, sc in enumerate(scenes):
        n = int(round(sc.dur * FPS)); fade = 7; fpath = os.path.join(tmpd, f"s{idx}.mp4")
        p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                              "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", fpath + ".tmp.mp4"], stdin=subprocess.PIPE)
        for i in range(n):
            img = sc.draw(i / FPS)
            k = min(1, (i + 1) / fade, (n - i) / fade)
            if k < 1: img = Image.eval(img, lambda v, k=k: int(v * k))
            p.stdin.write(img.tobytes())
        p.stdin.close()
        if p.wait() != 0: raise SystemExit("ffmpeg failed")
        os.replace(fpath + ".tmp.mp4", fpath); files.append(fpath)
        cues += [(k, t0 + s) for k, s in sc.cues()]; t0 += n / FPS
    lst = os.path.join(tmpd, "list.txt")
    with open(lst, "w") as f: f.write("".join(f"file '{x}'\n" for x in files))
    silent = os.path.join(tmpd, "silent.mp4"); wav = os.path.join(tmpd, "a.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", silent], check=True)
    make_audio(cues, t0, wav, seed=spec.get("music", 0))
    tmp_out = out_path + ".tmp.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", silent, "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "160k", "-shortest", "-movflags", "+faststart", tmp_out], check=True)
    os.replace(tmp_out, out_path)
    return t0

def stills(spec, outdir):
    os.makedirs(outdir, exist_ok=True); paths = []
    for i, sc in enumerate(build(spec)):
        p = os.path.join(outdir, f"still_{i}.png"); sc.draw(sc.dur - 0.3).save(p); paths.append(p)
    return paths

if __name__ == "__main__":
    spec = json.load(open(sys.argv[1]))
    if len(sys.argv) > 3 and sys.argv[2] == "--stills": print(stills(spec, sys.argv[3]))
    else: print("duration", render(spec, sys.argv[2]))
