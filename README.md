# 永和：一座花園城市的消失

一部以 3D 重建講述永和（新北市）歷史的紀錄短片：從 1955 年的「花園城市」都市計畫，到成為全台灣人口最密集的行政區。畫面為風格化的低多邊形城市，以 Blender Cycles 渲染；正體中文旁白與字幕。

## 檔案結構

| 路徑 | 內容 |
|---|---|
| `research/sources.md` | 考據筆記：年表、七座公園的去向、存疑之處；旁白中的每項事實都能在此找到出處 |
| `blender/geo.py` | 示意地理：新店溪、瓦磘溝界線、七座計畫公園、主要道路、歷年人口表 |
| `blender/layout.py` | 產生地面遮罩與約七萬四千個建築基地，每個基地有興建／拆除年份 → `build/layout.npz` |
| `blender/build_scene.py` | 建立 `build/yonghe.blend`：地形、程序化材質，以及由單一 `year` 屬性驅動的幾何節點城市 |
| `blender/storyboard.py` | 18 個鏡頭：旁白文字、攝影機路徑、年代／藍圖／舊公園／夜景曲線、畫面字卡 |
| `blender/curves.py` | 關鍵影格曲線（渲染與合成共用） |
| `blender/render.py` | 為單一鏡頭設定動畫並渲染畫格或靜態圖 |
| `pipeline/tts.py` | 以 Gemini TTS 逐鏡生成旁白 → `build/audio/<鏡頭>.wav`；加上 `--verify` 時，每次錄音都會交給 Gemini 轉錄比對（`check_audio.py`），唸錯就重錄 |
| `pipeline/score.py` | 以 Lyria 3 依五個段落生成配樂，依剪輯長度裁切並交叉淡化 → `build/score.wav` |
| `pipeline/modal_render.py` | 在 Modal 上平行渲染（L4 GPU、OptiX）；另有 `::upload` 上傳場景、`::stills` 試渲靜態圖 |
| `pipeline/compose.py` | 最終合成：畫格＋字幕、年份與人口計數、跟隨 3D 場景的地名標籤、章節字卡、溶接、底片顆粒、旁白壓低配樂的混音 → `build/yonghe.mp4` |
| `pipeline/contact.py` | 把試渲靜態圖排成一張總覽圖 |
| `assets/fonts/` | 標題與字幕用的思源宋體 Noto Serif TC（OFL 授權） |

## 建置場景

```bash
uv venv -p 3.11 .venv && uv pip install --python .venv bpy==5.0.1 numpy scipy pillow
# 無頭模式的 Cycles 不需要 GPU；EEVEE 則需要 libegl1
.venv/bin/python blender/layout.py
.venv/bin/python blender/build_scene.py
.venv/bin/python blender/render.py --shot S12 --still 0.5 --samples 8 --res 640x360 --out build/stills
```

## 完整流程

```bash
pip install 'modal[api-proxy-support]'   # 在 HTTPS proxy 後面，Modal 需要 python-socks 才能連線
export MODAL_TOKEN_ID=... MODAL_TOKEN_SECRET=... GEMINI_API_KEY=...
.venv/bin/python blender/layout.py && .venv/bin/python blender/build_scene.py
python pipeline/tts.py --verify                      # 生成旁白，鏡頭長度隨旁白決定
python pipeline/score.py                             # 依剪輯長度生成配樂
modal run pipeline/modal_render.py::upload           # 場景上傳到 volume yonghe-assets
modal run pipeline/modal_render.py::stills           # （選用）每個鏡頭試渲靜態圖
modal run --detach pipeline/modal_render.py::main --samples 64
modal volume get yonghe-frames / build/frames
python pipeline/compose.py                           # → build/yonghe.mp4
```

渲染規格：1080p、每像素 64 次取樣加降噪，10 張 L4 平行渲染；白天鏡頭每格約 2–3 秒，夜景每格約 5 秒，全片約 7,300 格。窗戶與路燈只作為可見的發光面、不當成光源取樣，夜景渲染時間因此減半，畫面上看不出差別。

交付版另外做響度標準化（-16 LUFS）與壓縮：

```bash
ffmpeg -i build/yonghe.mp4 -c:v libx264 -preset slow -crf 22 -tune grain -af loudnorm=I=-16:TP=-1.5:LRA=11 \
       -c:a aac -b:a 256k -movflags +faststart build/yonghe_final_1080p.mp4
```

## 製作狀態（2026-10-25）

已完成：考據、場景、18 段旁白（Gemini TTS，逐段轉錄核對）、五段配樂（Lyria 3）、全片 1080p 渲染與合成，成片長 5 分 09 秒。
