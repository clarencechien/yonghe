"""Ask Gemini to transcribe a narration WAV and rate the delivery (QA, since
nobody listens to the takes during an unattended run)."""
import base64, json, os, sys, urllib.request

def check(path, expected, model="gemini-3.1-pro-preview"):
    key = os.environ.get("GEMINI_API_KEY") or os.environ["gemini_key"]
    audio = base64.b64encode(open(path, "rb").read()).decode()
    prompt = ("這是一段紀錄片旁白錄音。請以 JSON 回答："
              '{"transcript": 逐字繁體中文轉錄, "matches_script": 與下列稿子是否逐字一致(true/false), '
              '"differences": 列出唸錯、漏唸、多唸之處, "accent": 口音描述, "pace": 語速評價, '
              '"long_pauses": 是否有不自然的長停頓, "quality_1to10": 作為紀錄片旁白的整體分數}\n稿子：' + expected)
    body = dict(contents=[dict(parts=[dict(text=prompt), dict(inlineData=dict(mimeType="audio/wav", data=audio))])],
                generationConfig=dict(responseMimeType="application/json"))
    req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                                 data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": key})
    d = json.load(urllib.request.urlopen(req, timeout=300))
    return json.loads(d["candidates"][0]["content"]["parts"][0]["text"])

if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "blender"))
    import storyboard
    for p in sys.argv[1:]:
        sid = os.path.basename(p)[:3]
        print(p, json.dumps(check(p, storyboard.get(sid)["text"]), ensure_ascii=False))
