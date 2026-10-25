"""Render storyboard shots on Modal in parallel (CPU containers).

    modal run pipeline/modal_render.py --shots S01,S02 --res 1920x1080 --samples 16

Needs MODAL_TOKEN_ID / MODAL_TOKEN_SECRET in the environment and network
access to api.modal.com. Not yet tested end to end (the first session had
no Modal credentials); see README.md.
"""
import os
import subprocess

import modal

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CHUNK = 24  # frames per container call

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libegl1", "libgl1", "libxrender1", "libxi6", "libxkbcommon0", "libsm6")
    .pip_install("bpy==5.0.1", "numpy", "scipy", "pillow")
    .add_local_dir(os.path.join(ROOT, "blender"), "/work/blender")
    .add_local_file(os.path.join(ROOT, "build", "yonghe.blend"), "/work/build/yonghe.blend")
    .add_local_dir(os.path.join(ROOT, "build"), "/work/build", ignore=["frames/**", "stills/**", "*.blend1"])
)
app = modal.App("yonghe-render", image=image)
vol = modal.Volume.from_name("yonghe-frames", create_if_missing=True)


@app.function(cpu=16, memory=16384, timeout=3600, volumes={"/frames": vol})
def render_chunk(shot: str, f0: int, f1: int, res: str, samples: int):
    subprocess.run(["python", "/work/blender/render.py", "--shot", shot, "--frames", f"{f0}:{f1}",
                    "--res", res, "--samples", str(samples), "--out", "/frames",
                    "--blend", "/work/build/yonghe.blend"], check=True)
    vol.commit()
    return shot, f0, f1


@app.local_entrypoint()
def main(shots: str = "", res: str = "1920x1080", samples: int = 16):
    import sys
    sys.path.insert(0, os.path.join(ROOT, "blender"))
    import storyboard
    ids = shots.split(",") if shots else [s["id"] for s in storyboard.SHOTS]
    jobs = []
    for sid in ids:
        n = int(round(storyboard.duration(storyboard.get(sid)) * 24))
        jobs += [(sid, a, min(a + CHUNK, n), res, samples) for a in range(0, n, CHUNK)]
    for sid, a, b in render_chunk.starmap(jobs):
        print("done", sid, a, b)
    print("download with: modal volume get yonghe-frames / build/frames")
