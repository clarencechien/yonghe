"""Final assembly: rendered frames + overlays + subtitles + narration + score.

    python pipeline/compose.py [--frames build/frames] [--out build/yonghe.mp4]
                               [--shots S01,S02] [--preview 0.5]

Overlays are drawn here rather than in Blender so typography stays crisp
and can be revised without re-rendering. 3D-anchored labels are projected
with the same camera curves render.py keys, so they track the scene.
"""
import argparse
import math
import multiprocessing
import os
import re
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "blender"))
import geo  # noqa: E402
import storyboard  # noqa: E402
from curves import cr, ease, lin  # noqa: E402

FPS = 24
W, H = 1920, 1080
XFADE = 12            # frames of dissolve between shots
VO_LEAD = 0.5         # narration starts this long into its shot
RATE = 48000
FONT_R = os.path.join(ROOT, "assets", "fonts", "NotoSerifTC-regular.ttf")
FONT_B = os.path.join(ROOT, "assets", "fonts", "NotoSerifTC-semi_bold.ttf")
_fonts = {}


def font(size, bold=False):
    k = (size, bold)
    if k not in _fonts:
        _fonts[k] = ImageFont.truetype(FONT_B if bold else FONT_R, size)
    return _fonts[k]


# ---------------------------------------------------------------- timeline
def timeline(ids):
    out, t = [], 0
    for i, sid in enumerate(ids):
        shot = storyboard.get(sid)
        n = max(2, int(round(storyboard.duration(shot) * FPS)))
        start = t if i == 0 else t - XFADE
        out.append(dict(shot=shot, start=start, n=n))
        t = start + n
    return out, t


# ---------------------------------------------------------------- camera
def camera(shot, t):
    te = ease(t, shot.get("ease", 0.65))
    pos = np.array(cr(shot["cam"], te), float)
    tgt = np.array(cr(shot["target"], te), float)
    lens = cr(shot.get("lens", 35.0), te)
    f = tgt - pos
    f /= np.linalg.norm(f)
    r = np.cross(f, (0, 0, 1.0))
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    return pos, f, r, u, lens / 36.0 * W


def project(cam, p):
    pos, f, r, u, fpx = cam
    d = np.array(p, float) - pos
    z = d @ f
    if z <= 1:
        return None
    return W / 2 + fpx * (d @ r) / z, H / 2 - fpx * (d @ u) / z


# ---------------------------------------------------------------- drawing
def fade(t, a, b, ramp=0.06):
    if t < a or t > b:
        return 0.0
    k = min((t - a) / ramp if a > 0 else 1.0, (b - t) / ramp if b < 1 else 1.0, 1.0)
    return k * k * (3 - 2 * k)


class Layer:
    """RGBA text layer with a soft drop shadow."""

    def __init__(self):
        self.img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    def text(self, xy, s, size, alpha, bold=False, anchor="la", fill=(245, 240, 228)):
        if alpha > 0.01:
            self.d.text(xy, s, font=font(size, bold), anchor=anchor, fill=(*fill, int(255 * alpha)))

    def line(self, pts, alpha, width=2, fill=(245, 240, 228)):
        if alpha > 0.01:
            self.d.line(pts, fill=(*fill, int(255 * alpha)), width=width)

    def circle(self, c, r, alpha, width=2, fill=None, outline=(245, 240, 228)):
        if alpha > 0.01:
            box = (c[0] - r, c[1] - r, c[0] + r, c[1] + r)
            self.d.ellipse(box, outline=(*outline, int(255 * alpha)), width=width,
                           fill=None if fill is None else (*fill, int(150 * alpha)))

    def composite(self, frame):
        a = self.img.split()[3]
        if a.getbbox() is None:
            return frame
        for radius, k in ((14, 0.7), (3, 0.9)):
            sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            sh.putalpha(a.filter(ImageFilter.GaussianBlur(radius)).point(lambda v, k=k: int(min(255, v * k * 1.6))))
            frame = Image.alpha_composite(frame, sh)
        return Image.alpha_composite(frame, self.img)


def fmt_int(v):
    return f"{int(round(v)):,}"


def population(year):
    tab = geo.POPULATION
    if year < tab[0][0]:
        return None
    for (y0, p0), (y1, p1) in zip(tab[:-1], tab[1:]):
        if year <= y1:
            return p0 + (p1 - p0) * (year - y0) / (y1 - y0)
    return tab[-1][1]


def draw_overlays(L, shot, t, cam):
    yr = lin(shot.get("year", storyboard.DEFAULTS["year"]), t)
    for ov in shot.get("overlay", []):
        a = fade(t, *ov["t"])
        if a <= 0:
            continue
        k = ov["kind"]
        if k == "caption":
            L.text((96, 96), ov["text"], 36, a * 0.9)
        elif k == "title":
            L.text((W / 2, H / 2 - 40), ov["text"], 168, a, bold=True, anchor="mm")
            L.line([(W / 2 - 160, H / 2 + 80), (W / 2 + 160, H / 2 + 80)], a * 0.7, 2)
            L.text((W / 2, H / 2 + 130), ov["sub"], 50, a, anchor="mm")
        elif k == "year":
            L.text((W - 96, 80), ov["text"], 76, a, bold=True, anchor="ra")
        elif k == "yearcount":
            L.text((W - 96, 80), str(int(math.floor(yr))), 76, a, bold=True, anchor="ra")
        elif k == "popcount":
            p = population(yr)
            if p is not None:
                L.text((W - 96, 180), "人口", 30, a * 0.85, anchor="ra")
                L.text((W - 96, 220), fmt_int(p), 54, a, anchor="ra")
        elif k == "label":
            pt = project(cam, ov["at"])
            if pt is None or not (-200 < pt[0] < W + 200 and -200 < pt[1] < H + 200):
                continue
            x, y = pt
            top = y - 110
            L.circle((x, y), 7, a, width=3)
            L.line([(x, y - 9), (x, top)], a * 0.9, 2)
            L.text((x + 14, top - 6), ov["text"], 40, a, bold=True, anchor="ls")
        elif k == "parknums":
            for pid, c, rad, *_ in geo.PARKS:
                pt = project(cam, (*c, 5))
                if pt is None:
                    continue
                L.circle(pt, 30, a, width=3, fill=(30, 50, 45))
                L.text(pt, str(pid), 34, a, bold=True, anchor="mm")
        elif k == "bignum":
            L.text((W / 2, H / 2 + 260), ov["text"], 92, a, bold=True, anchor="mm")
        elif k == "stat":
            L.text((96, 150), ov["text"], 52, a, bold=True, anchor="la")


# ---------------------------------------------------------------- subtitles
def subtitle_chunks(text, maxlen=22):
    parts = [p for p in re.split(r"(?<=[。；：，、！？])", text) if p]
    chunks, cur = [], ""
    for p in parts:
        if cur and len(cur) + len(p) > maxlen:
            chunks.append(cur)
            cur = p
        else:
            cur += p
    if cur:
        chunks.append(cur)
    return chunks


def subtitle_times(sid, text):
    """(t0, t1, text) in seconds from narration start, split at pauses."""
    chunks = subtitle_chunks(text)
    pcm = load_wav(os.path.join(storyboard.AUDIO, f"{sid}.wav"), 24000)
    total = len(pcm) / 24000
    # character-proportional split, then snap each boundary to the nearest pause
    env = np.abs(pcm)
    hop = 240
    e = np.array([env[i:i + hop].mean() for i in range(0, len(env) - hop, hop)])
    quiet = e < (0.06 * np.percentile(e, 95))
    n = sum(len(c) for c in chunks)
    out, acc = [], 0
    bounds = [0.0]
    for c in chunks[:-1]:
        acc += len(c)
        guess = acc / n * total
        gi = int(guess * 100)
        lo, hi = max(gi - 60, 1), min(gi + 60, len(quiet) - 1)
        cands = [i for i in range(lo, hi) if quiet[i]]
        bounds.append(min(cands, key=lambda i: abs(i - gi)) / 100 if cands else guess)
    bounds.append(total)
    for c, a, b in zip(chunks, bounds[:-1], bounds[1:]):
        # broadcast style: no punctuation, a full-width space for pauses
        c = re.sub(r"[，、；：。！？]+", "　", c).strip("　")
        out.append((a, b, c))
    return out


def draw_subtitle(L, s, alpha):
    L.text((W / 2, H - 92), s, 46, alpha, anchor="ms")


# ---------------------------------------------------------------- audio
def load_wav(path, rate):
    with wave.open(path) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32768
        if w.getnchannels() == 2:
            x = x.reshape(-1, 2).mean(1)
        assert w.getframerate() == rate, (path, w.getframerate())
    return x


def decode(path, rate=RATE, ch=2):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", str(ch),
                          "-ar", str(rate), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, ch)


def mix_audio(tl, nframes, score_path, out):
    n = int(nframes / FPS * RATE) + RATE
    vo = np.zeros(n, np.float32)
    for e in tl:
        p = os.path.join(storyboard.AUDIO, f"{e['shot']['id']}.wav")
        x = decode(p, RATE, 1)[:, 0]
        i = int((e["start"] / FPS + VO_LEAD) * RATE)
        vo[i:i + len(x)] += x[: n - i]
    # broadcast loudness: narration peaks around -3 dBFS
    vo *= 0.7 / max(np.abs(vo).max(), 1e-6)
    mix = np.repeat(vo[:, None], 2, 1)
    if score_path and os.path.exists(score_path):
        mus = decode(score_path)[:n]
        mus = np.pad(mus, ((0, n - len(mus)), (0, 0)))
        # duck the score under the voice with a smoothed envelope
        blk = RATE // 20
        act = np.abs(vo[: len(vo) // blk * blk]).reshape(-1, blk).max(1) > 0.02
        act = np.convolve(act.astype(float), np.ones(14) / 14, "same")  # ~0.7 s smoothing
        g = 0.42 - 0.27 * np.clip(act * 1.5, 0, 1)
        g = np.repeat(g, blk)
        g = np.pad(g, (0, n - len(g)), constant_values=g[-1])
        mus *= (g / max(np.abs(mus).max(), 1e-6))[:, None]
        mix += mus
    fade_n = int(3 * RATE)
    end = int(nframes / FPS * RATE)
    mix = mix[:end]
    mix[-fade_n:] *= np.linspace(1, 0, fade_n)[:, None]
    mix = np.clip(mix, -1, 1)
    with wave.open(out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((mix * 32767).astype("<i2").tobytes())


# ---------------------------------------------------------------- frames
def load_frame(frames, sid, f, n):
    p = os.path.join(frames, sid, f"{min(f, n - 1):05d}.png")
    if not os.path.exists(p):
        return Image.new("RGBA", (W, H), (8, 8, 10, 255))
    im = Image.open(p).convert("RGBA")
    return im if im.size == (W, H) else im.resize((W, H), Image.LANCZOS)


def grade(im, rng, vig, dim=0.0):
    """Subtle film grain and vignette; dim darkens the frame under big titles."""
    a = np.asarray(im.convert("RGB"), np.float32)
    a *= (vig * (1 - dim))[..., None]
    a += rng.normal(0, 2.2, a.shape[:2])[..., None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).convert("RGBA")


def endcard(t, dur):
    im = Image.new("RGBA", (W, H), (6, 6, 8, 255))
    L = Layer()
    a = fade(t / dur, 0.0, 1.0, 0.1)
    L.text((W / 2, 300), "永和：一座花園城市的消失", 64, a, bold=True, anchor="mm")
    lines = [
        "主要參考：廖盈琪《昨日的明日花園城市──永和都市計畫之移植與形構》（臺大城鄉所碩士論文，1998）",
        "新北市政府《變更永和都市計畫（第一次通盤檢討）》　《永和鎮志》《永和市志》",
        "《臺灣地名辭書．臺北縣》　中和鄉志　維基百科「永和區」歷年人口",
        "3D 地形與建築為依史料重建之示意，非測繪精度；完整出處見 research/sources.md",
        "旁白：Gemini TTS　配樂：Lyria　渲染：Blender Cycles",
    ]
    for i, s in enumerate(lines):
        L.text((W / 2, 470 + i * 64), s, 30, a * 0.85, anchor="mm")
    return L.composite(im)


_FRAME = None


def _frame_bytes(g):
    return _FRAME(g).tobytes()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", default=os.path.join(ROOT, "build", "frames"))
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "yonghe.mp4"))
    ap.add_argument("--score", default=os.path.join(ROOT, "build", "score.wav"))
    ap.add_argument("--shots", default="")
    ap.add_argument("--preview", type=float, default=None, help="write one PNG per shot at t")
    ap.add_argument("--crf", type=int, default=16)
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = ap.parse_args()
    ids = a.shots.split(",") if a.shots else [s["id"] for s in storyboard.SHOTS]
    tl, total = timeline(ids)
    end_n = int(storyboard.ENDCARD["seconds"] * FPS) if not a.shots else 0
    nframes = total + end_n
    subs = []
    chapters = []
    prev = None
    for e in tl:
        sid = e["shot"]["id"]
        t0 = e["start"] / FPS + VO_LEAD
        subs += [(t0 + s0, t0 + s1, s) for s0, s1, s in subtitle_times(sid, e["shot"]["text"])]
        ch = e["shot"].get("chapter")
        if ch != prev and prev is not None and e["shot"]["id"] != "S02":
            chapters.append((e["start"] / FPS + 0.3, ch))
        prev = ch

    # one subtitle at a time: lead the voice slightly, never overlap the next
    subs.sort()
    subs = [(max(s0 - 0.1, subs[i - 1][1] if i else 0), min(s1 + 0.25, subs[i + 1][0] - 0.1)
             if i + 1 < len(subs) else s1 + 0.25, s) for i, (s0, s1, s) in enumerate(subs)]

    yy, xx = np.mgrid[0:H, 0:W]
    r = np.hypot((xx - W / 2) / (W / 2), (yy - H / 2) / (H / 2))
    vig = 1 - 0.28 * np.clip(r - 0.45, 0, 1) ** 1.6
    # a soft dark band behind the subtitles
    vig *= 1 - 0.38 * np.clip((yy - H * 0.78) / (H * 0.22), 0, 1) ** 1.3
    vig = vig.astype(np.float32)
    def frame_at(g):
        rng = np.random.default_rng(g)
        live = [e for e in tl if e["start"] <= g < e["start"] + e["n"]]
        out = None
        for e in live:
            f = g - e["start"]
            t = f / max(e["n"] - 1, 1)
            im = load_frame(a.frames, e["shot"]["id"], f, e["n"])
            L = Layer()
            draw_overlays(L, e["shot"], t, camera(e["shot"], t))
            dim = max([0.0] + [0.45 * fade(t, *o["t"]) for o in e["shot"].get("overlay", [])
                               if o["kind"] in ("title", "bignum")])
            im = L.composite(grade(im, rng, vig, dim))
            if out is None:
                out = im
            else:  # dissolve into the next shot
                out = Image.blend(out, im, (f + 1) / (XFADE + 1))
        if out is None:
            out = endcard((g - total) / FPS, storyboard.ENDCARD["seconds"])
        sec = g / FPS
        L = Layer()
        for s0, s1, s in subs:
            if s0 <= sec <= s1:
                draw_subtitle(L, s, min(1.0, (sec - s0) / 0.12, (s1 - sec) / 0.12))
        for c0, ch in chapters:
            k = fade(sec, c0, c0 + 3.4, 0.6 / 3.4) if c0 <= sec <= c0 + 3.4 else 0
            if k:
                L.text((96, 96), ch, 52, k, bold=True)
                L.line([(96, 168), (196, 168)], k * 0.8, 2)
        return L.composite(out).convert("RGB")

    if a.preview is not None:
        os.makedirs(a.out, exist_ok=True)
        for e in tl:
            g = e["start"] + int(a.preview * (e["n"] - 1))
            frame_at(g).save(os.path.join(a.out, f"{e['shot']['id']}.png"))
        return

    wav = os.path.splitext(a.out)[0] + "_mix.wav"
    mix_audio(tl, nframes, a.score, wav)
    ff = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", wav,
                           "-c:v", "libx264", "-preset", "slow", "-crf", str(a.crf), "-pix_fmt", "yuv420p",
                           "-tune", "film", "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart",
                           "-shortest", a.out], stdin=subprocess.PIPE)
    global _FRAME
    _FRAME = frame_at
    with multiprocessing.get_context("fork").Pool(a.jobs) as pool:
        for g, buf in enumerate(pool.imap(_frame_bytes, range(nframes), chunksize=4)):
            ff.stdin.write(buf)
            if g % 240 == 0:
                print(f"{g}/{nframes}", flush=True)
    ff.stdin.close()
    ff.wait()
    print("wrote", a.out, f"{nframes / FPS:.1f}s")


if __name__ == "__main__":
    main()
