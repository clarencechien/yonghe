"""Original score with Lyria 3 (Gemini API): one cue per movement, cut to
the edit and joined with crossfades into build/score.wav.

    python pipeline/score.py [--force]

Cue lengths come from the same timeline compose.py uses, so run this after
the narration exists.
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.request
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import compose  # noqa: E402

OUT = os.path.join(compose.ROOT, "build", "score")
MODEL = "lyria-3-pro-preview"
PALETTE = ("Instrumental underscore for a Taiwanese public-television history documentary. "
           "Felt piano, warm string ensemble, soft pads, occasional distant erhu. "
           "No vocals, no lyrics, no drum kit, no sudden hits; leaves room for a narrator. ")
# (first shot of the movement, mood)
CUES = [
    ("S01", "Opening over a vast city at night: low sustained strings, sparse piano notes, "
            "a sense of quiet density and mystery. 60 bpm, D minor."),
    ("S03", "Pastoral memory of river sandbanks and rice paddies centuries ago: gentle, airy, "
            "flowing piano arpeggios, soft erhu melody, morning light. 72 bpm, D major / modal."),
    ("S07", "Post-war refugees and a new town plan: restrained, hopeful yet uncertain; "
            "strings build slowly under a simple piano theme like drawing a blueprint. 76 bpm."),
    ("S12", "Three decades of explosive growth: a steady pulsing string ostinato and repeating "
            "piano figure that keeps adding layers, gaining tension and density, never triumphant. 92 bpm."),
    ("S16", "Present day and epilogue: reflective and bittersweet, the opening theme returns warmer, "
            "piano and cello, slowly resolving to a quiet ending with a long final chord. 66 bpm."),
]
XF = 3.0  # seconds of crossfade between cues


def generate(prompt, seconds, key):
    body = dict(contents=[dict(parts=[dict(text=f"{PALETTE}{prompt} About {int(seconds)} seconds long.")])])
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
                "Content-Type": "application/json", "x-goog-api-key": key})
            d = json.load(urllib.request.urlopen(req, timeout=600))
            for p in d["candidates"][0]["content"]["parts"]:
                if "inlineData" in p:
                    return base64.b64decode(p["inlineData"]["data"])
            raise RuntimeError(str(d)[:300])
        except Exception as e:
            print("  retry", attempt, e)
            time.sleep(15 * (attempt + 1))
    raise RuntimeError("Lyria failed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    key = os.environ.get("GEMINI_API_KEY") or os.environ["gemini_key"]
    os.makedirs(OUT, exist_ok=True)
    tl, total = compose.timeline([s["id"] for s in compose.storyboard.SHOTS])
    starts = {e["shot"]["id"]: e["start"] / compose.FPS for e in tl}
    end = total / compose.FPS + compose.storyboard.ENDCARD["seconds"]
    bounds = [starts[c[0]] for c in CUES] + [end]
    R = compose.RATE
    out = np.zeros((int(end * R) + R, 2), np.float32)
    for i, (sid, mood) in enumerate(CUES):
        t0, t1 = bounds[i], bounds[i + 1]
        need = t1 - t0 + (XF if i + 1 < len(CUES) else 0)
        mp3 = os.path.join(OUT, f"cue{i + 1}_{sid}.mp3")
        if a.force or not os.path.exists(mp3):
            open(mp3, "wb").write(generate(mood, need + 8, key))
        x = compose.decode(mp3).copy()
        x /= max(np.sqrt(np.mean(x ** 2)) * 8, 1e-6)  # loudness-match cues (RMS)
        n = int(need * R)
        if len(x) < n:  # too short: hold the tail
            print(f"  cue {i + 1} short: {len(x) / R:.1f}s < {need:.1f}s")
            x = np.pad(x, ((0, n - len(x)), (0, 0)))
        x = x[:n].copy()
        xf = int(XF * R)
        if i > 0:
            x[:xf] *= np.linspace(0, 1, xf)[:, None]
        if i + 1 < len(CUES):
            x[-xf:] *= np.linspace(1, 0, xf)[:, None]
        else:
            fo = int(6 * R)
            x[-fo:] *= np.linspace(1, 0, fo)[:, None] ** 2
        s = int(t0 * R)
        out[s:s + len(x)] += x[: len(out) - s]
        print(f"cue {i + 1} {sid}: {t0:.1f}-{t1:.1f}s")
    out /= max(np.abs(out).max(), 1e-6) / 0.9
    with wave.open(os.path.join(compose.ROOT, "build", "score.wav"), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(R)
        w.writeframes((out * 32767).astype("<i2").tobytes())
    print("wrote build/score.wav", f"{end:.1f}s")


if __name__ == "__main__":
    main()
