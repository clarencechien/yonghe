"""Narration with Gemini TTS: one WAV per shot in build/audio/<id>.wav.

    python pipeline/tts.py [--shots S01,S02] [--voice Charon] [--model ...] [--force]

Reads the key from GEMINI_API_KEY (or gemini_key). Output is 24 kHz mono
16-bit PCM; leading/trailing silence is trimmed so shot timing follows
the spoken words.
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

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "blender"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import storyboard  # noqa: E402
import check_audio  # noqa: E402

OUT = os.path.join(ROOT, "build", "audio")
RATE = 24000
STYLE = ("你是台灣公共電視歷史紀錄片的旁白。用台灣口音的標準國語，"
         "語氣沉穩、溫和、略帶感懷，速度從容，句與句之間自然停頓，"
         "數字清楚。請只唸出下面這段旁白：\n\n")


def synth(text, voice, model, key):
    body = dict(contents=[dict(parts=[dict(text=STYLE + text)])],
                generationConfig=dict(responseModalities=["AUDIO"], speechConfig=dict(
                    voiceConfig=dict(prebuiltVoiceConfig=dict(voiceName=voice)))))
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    for attempt in range(5):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
            "Content-Type": "application/json", "x-goog-api-key": key})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                d = json.load(r)
            part = d["candidates"][0]["content"]["parts"][0]["inlineData"]
            return np.frombuffer(base64.b64decode(part["data"]), dtype="<i2")
        except Exception as e:  # rate limits / transient errors
            print("  retry", attempt, e)
            time.sleep(10 * (attempt + 1))
    raise RuntimeError("TTS failed")


def trim(pcm, thresh=300, keep=0.08):
    loud = np.nonzero(np.abs(pcm.astype(np.int32)) > thresh)[0]
    if not len(loud):
        return pcm
    k = int(keep * RATE)
    return pcm[max(loud[0] - k, 0):loud[-1] + k]


def write(path, pcm):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", default="")
    ap.add_argument("--voice", default="Charon")
    ap.add_argument("--model", default="gemini-2.5-pro-preview-tts")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--verify", action="store_true", help="transcribe each take with Gemini; retake on mismatch")
    ap.add_argument("--takes", type=int, default=4)
    a = ap.parse_args()
    key = os.environ.get("GEMINI_API_KEY") or os.environ["gemini_key"]
    os.makedirs(a.out, exist_ok=True)
    ids = a.shots.split(",") if a.shots else [s["id"] for s in storyboard.SHOTS]
    for sid in ids:
        path = os.path.join(a.out, f"{sid}.wav")
        if os.path.exists(path) and not a.force:
            continue
        text = storyboard.get(sid)["text"]
        best = None
        for take in range(a.takes):
            pcm = trim(synth(text, a.voice, a.model, key))
            write(path, pcm)
            if not a.verify:
                best = (0, pcm)
                break
            qa = check_audio.check(path, text)
            qa = qa[0] if isinstance(qa, list) else qa
            ok = bool(qa.get("matches_script")) and not qa.get("long_pauses")
            score = (ok, float(qa.get("quality_1to10") or 0))
            print(f"  {sid} take {take}: match={ok} q={score[1]} {qa.get('differences')}", flush=True)
            if best is None or score > best[0]:
                best = (score, pcm)
            if ok and score[1] >= 7:
                break
        write(path, best[1])
        print(sid, f"{len(best[1]) / RATE:.1f}s", flush=True)


if __name__ == "__main__":
    main()
