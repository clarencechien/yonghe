# 永和：一座花園城市的消失

A 3D documentary on Yonghe (永和, New Taipei): from the 1955 "garden city"
plan to the most densely populated district in Taiwan. Stylised low-poly
city, rendered with Blender Cycles; Traditional Chinese narration.

## Layout

| Path | What |
|---|---|
| `research/sources.md` | Sourced timeline, park fates, open questions; every narrated fact is cited here |
| `blender/geo.py` | Schematic geography: river, creek boundary, 7 planned parks, arterials, population table |
| `blender/layout.py` | Generates ground masks + ~74k building sites, each with birth/death years → `build/layout.npz` |
| `blender/build_scene.py` | Builds `build/yonghe.blend`: terrain, procedural materials, geometry-nodes city driven by one `year` property |
| `blender/storyboard.py` | 18 shots: narration text, camera paths, year/blueprint/ghost/night curves, overlays |
| `blender/render.py` | Animates one shot and renders frames or a still |
| `pipeline/modal_render.py` | Parallel shot rendering on Modal (untested, needs credentials) |
| `assets/fonts/` | Noto Serif TC (OFL) for titles and subtitles |

## Build

```bash
uv venv -p 3.11 .venv && uv pip install --python .venv bpy==5.0.1 numpy scipy pillow
# headless Cycles needs no GPU; EEVEE would need libegl1
.venv/bin/python blender/layout.py
.venv/bin/python blender/build_scene.py
.venv/bin/python blender/render.py --shot S12 --still 0.5 --samples 8 --res 640x360 --out build/stills
```

## Status (2026-10-25)

Done: research notes, geography/layout generator, scene builder, storyboard
and narration script, look development (stills of every era render).

Remaining:
1. Narration TTS with Gemini (`GEMINI_API_KEY`) → `build/audio/<shot>.wav`;
   shot lengths then follow the audio automatically (`storyboard.duration`).
2. Render all shots. Locally (4 CPU) Cycles costs ~1 s per sample per 720p
   frame (8 spp ≈ 13 s/frame, ~6,300 frames), so the full film should be
   rendered on Modal (`pipeline/modal_render.py`). Note: changing samples
   after the first render in a persistent-data session has no effect —
   set them before rendering.
3. Overlays (year counter, population counter, labels, titles, subtitles),
   ambient score, and final ffmpeg assembly.
