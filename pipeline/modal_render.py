"""Render storyboard shots on Modal in parallel.

    modal run pipeline/modal_render.py::upload            # once per scene rebuild
    modal run pipeline/modal_render.py --shots S01,S02 --res 1920x1080 --samples 64
    modal run pipeline/modal_render.py::bench --shot S12   # CPU vs GPU timing

The scene (build/yonghe.blend plus its EXR masks, ~850 MB) lives in the
volume "yonghe-assets"; frames go to "yonghe-frames" as <shot>/<frame>.png.
Shot lengths are computed locally from build/audio and passed explicitly,
so the containers do not need the narration.

Needs MODAL_TOKEN_ID / MODAL_TOKEN_SECRET. Behind an HTTPS proxy the
client needs `pip install 'modal[api-proxy-support]'`.
"""
import os
import subprocess
import sys
import time

import modal

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
BUILD = os.path.join(ROOT, "build")
CHUNK = 12  # frames per call: persistent data amortises scene load over a chunk
ASSETS = ["yonghe.blend", "tex_gyear.exr", "tex_plan.exr", "tex_roads.exr", "tex_zone.exr"]

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libegl1", "libgl1", "libxrender1", "libxi6", "libxkbcommon0", "libsm6", "libxfixes3", "libxext6")
    .pip_install("bpy==5.0.1", "numpy", "scipy", "pillow")
    .add_local_dir(os.path.join(ROOT, "blender"), "/work/blender", ignore=["__pycache__"])
)
app = modal.App("yonghe-render", image=image)
assets = modal.Volume.from_name("yonghe-assets", create_if_missing=True)
frames = modal.Volume.from_name("yonghe-frames", create_if_missing=True)
VOLS = {"/work/build": assets, "/frames": frames}


def _render(shot, f0, f1, res, samples, dur, device, out="/frames", extra=()):
    cmd = ["python", "/work/blender/render.py", "--shot", shot, "--frames", f"{f0}:{f1}",
           "--res", res, "--samples", str(samples), "--out", out, "--duration", str(dur),
           "--blend", "/work/build/yonghe.blend", "--device", device, *extra]
    t = time.time()
    subprocess.run(cmd, check=True)
    return time.time() - t


@app.function(cpu=16, memory=24576, timeout=3600, volumes=VOLS, retries=2)
def render_cpu(shot: str, f0: int, f1: int, res: str, samples: int, dur: float):
    s = _render(shot, f0, f1, res, samples, dur, "CPU")
    frames.commit()
    return shot, f0, f1, s


@app.function(gpu="L4", cpu=4, memory=24576, timeout=3600, volumes=VOLS, retries=2)
def render_gpu(shot: str, f0: int, f1: int, res: str, samples: int, dur: float):
    s = _render(shot, f0, f1, res, samples, dur, "OPTIX")
    frames.commit()
    return shot, f0, f1, s


@app.local_entrypoint()
def upload():
    with assets.batch_upload(force=True) as b:
        for f in ASSETS:
            b.put_file(os.path.join(BUILD, f), f"/{f}")
    print("uploaded", ASSETS)


def _jobs(ids, res, samples):
    sys.path.insert(0, os.path.join(ROOT, "blender"))
    import storyboard
    jobs = []
    for sid in ids:
        dur = storyboard.duration(storyboard.get(sid))
        n = max(2, int(round(dur * 24)))
        jobs += [(sid, a, min(a + CHUNK, n), res, samples, dur) for a in range(0, n, CHUNK)]
    return jobs


@app.local_entrypoint()
def bench(shot: str = "S12", res: str = "1920x1080", samples: int = 64):
    (job,) = [j for j in _jobs([shot], res, samples) if j[1] == 0]
    job = (job[0], 0, 3, *job[3:])
    for fn in (render_gpu, render_cpu):
        print(fn.remote(*job))


@app.local_entrypoint()
def main(shots: str = "", res: str = "1920x1080", samples: int = 64, gpu: bool = True):
    sys.path.insert(0, os.path.join(ROOT, "blender"))
    import storyboard
    ids = shots.split(",") if shots else [s["id"] for s in storyboard.SHOTS]
    jobs = _jobs(ids, res, samples)
    print(len(jobs), "chunks,", sum(j[2] - j[1] for j in jobs), "frames")
    fn = render_gpu if gpu else render_cpu
    t = time.time()
    for i, (sid, a, b, s) in enumerate(fn.starmap(jobs, return_exceptions=False)):
        print(f"[{i + 1}/{len(jobs)}] {sid} {a}-{b} {s:.0f}s  elapsed {time.time() - t:.0f}s", flush=True)
    print("download with: modal volume get yonghe-frames / build/frames")


@app.function(gpu="L4", cpu=4, memory=24576, timeout=1800, volumes=VOLS)
def still_gpu(shot: str, t: float, res: str, samples: int, dur: float):
    out = "/tmp/stills"
    subprocess.run(["python", "/work/blender/render.py", "--shot", shot, "--still", str(t), "--res", res,
                    "--samples", str(samples), "--out", out, "--duration", str(dur),
                    "--blend", "/work/build/yonghe.blend", "--device", "OPTIX"], check=True,
                   stdout=subprocess.DEVNULL)
    return shot, t, open(f"{out}/{shot}_still_{t:.2f}.png", "rb").read()


@app.local_entrypoint()
def stills(shots: str = "", ts: str = "0.1,0.9", res: str = "1280x720", samples: int = 64,
           out: str = os.path.join(BUILD, "stills")):
    """Proof frames for look development: every shot at a few points in time."""
    sys.path.insert(0, os.path.join(ROOT, "blender"))
    import storyboard
    ids = shots.split(",") if shots else [s["id"] for s in storyboard.SHOTS]
    jobs = [(sid, float(t), res, samples, storyboard.duration(storyboard.get(sid)))
            for sid in ids for t in ts.split(",")]
    os.makedirs(out, exist_ok=True)
    for sid, t, png in still_gpu.starmap(jobs):
        p = os.path.join(out, f"{sid}_{t:.2f}.png")
        open(p, "wb").write(png)
        print(p)
