"""Animate and render one shot of the storyboard.

    python blender/render.py --shot S03 [--frames 0:120] [--still 0.5]
                             [--res 1280x720] [--samples 24] [--out build/frames]

A shot is a dict in storyboard.SHOTS. Camera, look-at target, lens and
every scene control ("year", "bp", "night", ...) are given as keyframe
lists [(t, value), ...] with t in 0..1 of the shot; this script samples
them per frame (Catmull-Rom) and writes real keyframes, so the same .blend
renders identically locally and on Modal.
"""
import argparse
import math
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import storyboard  # noqa: E402

BUILD = os.path.join(HERE, "..", "build")
FPS = 24


def ease(t, k=0.65):
    s = t * t * (3 - 2 * t)
    return t + (s - t) * k


def cr(keys, t):
    """Catmull-Rom through (time, value) keys; values may be tuples."""
    if not isinstance(keys, (list, tuple)) or not keys or not isinstance(keys[0], (list, tuple)):
        return keys
    if len(keys) == 1 or t <= keys[0][0]:
        return keys[0][1]
    if t >= keys[-1][0]:
        return keys[-1][1]
    i = max(j for j in range(len(keys) - 1) if keys[j][0] <= t)
    t0, t1 = keys[i][0], keys[i + 1][0]
    u = (t - t0) / (t1 - t0)
    p1, p2 = keys[i][1], keys[i + 1][1]
    p0 = keys[i - 1][1] if i > 0 else p1
    p3 = keys[i + 2][1] if i + 2 < len(keys) else p2
    scalar = not isinstance(p1, (list, tuple))
    if scalar:
        p0, p1, p2, p3 = (p0,), (p1,), (p2,), (p3,)
    out = []
    for a, b, c, d in zip(p0, p1, p2, p3):
        out.append(0.5 * ((2 * b) + (-a + c) * u + (2 * a - 5 * b + 4 * c - d) * u * u
                          + (-a + 3 * b - 3 * c + d) * u ** 3))
    return out[0] if scalar else tuple(out)


def lin(keys, t):
    """Piecewise linear with smoothstep inside each segment (for controls)."""
    if not isinstance(keys, (list, tuple)) or not keys or not isinstance(keys[0], (list, tuple)):
        return keys
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys[:-1], keys[1:]):
        if t <= t1:
            u = (t - t0) / max(t1 - t0, 1e-9)
            u = u * u * (3 - 2 * u)
            return v0 + (v1 - v0) * u
    return keys[-1][1]


CONTROLS = ("year", "bp", "reveal", "ghost", "night", "fog")


def apply_shot(sc, shot, nframes):
    cam = sc.objects["Camera"]
    cam.animation_data_clear()
    sc.animation_data_clear()
    sc.frame_start, sc.frame_end = 0, nframes - 1
    look = shot.get("look", {})
    # sky / sun / haze (static per shot)
    sky = sc.world.node_tree.nodes["Sky Texture"]
    elev, azim = look.get("sun", (35, 200))
    sky.sun_elevation = math.radians(max(elev, -4))
    sky.sun_rotation = math.radians(azim)
    sc.world.node_tree.nodes["Background"].inputs["Strength"].default_value = look.get("sky", 0.25)
    sun = sc.objects["Sun"]
    sun.rotation_euler = (math.radians(90 - elev), 0, math.radians(azim + 90))
    sun.data.energy = look.get("sun_energy", 4.0 if elev > 5 else 0.0)
    sun.data.color = look.get("sun_color", (1.0, 0.95, 0.88))
    fc = look.get("fog_color", (0.62, 0.68, 0.76))
    sc["fog_r"], sc["fog_g"], sc["fog_b"] = fc
    sc.view_settings.exposure = look.get("exposure", 0.0)
    boat = sc.objects.get("SYS_boat")
    for f in range(nframes):
        t = f / max(nframes - 1, 1)
        te = ease(t, shot.get("ease", 0.65))
        pos = Vector(cr(shot["cam"], te))
        tgt = Vector(cr(shot["target"], te))
        cam.location = pos
        cam.rotation_mode = "QUATERNION"
        q = (tgt - pos).to_track_quat("-Z", "Y")
        roll = cr(shot.get("roll", 0.0), te)
        if roll:
            from mathutils import Quaternion
            q = q @ Quaternion((0, 0, 1), math.radians(roll))
        cam.rotation_quaternion = q
        cam.data.lens = cr(shot.get("lens", 35.0), te)
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_quaternion", frame=f)
        cam.data.keyframe_insert("lens", frame=f)
        for c in CONTROLS:
            if c in shot:
                sc[c] = float(lin(shot[c], t))
            elif c == "fog":
                sc[c] = float(look.get("fog", 0.00035))
            else:
                sc[c] = float(storyboard.DEFAULTS.get(c, 0.0))
            sc.keyframe_insert(f'["{c}"]', frame=f)
        if boat is not None and "boat" in shot:
            boat.location = (*cr(shot["boat"], t), -1.9)
            boat.keyframe_insert("location", frame=f)
    if cam.animation_data and cam.animation_data.action:
        for fcu in _fcurves(cam.animation_data.action):
            for kp in fcu.keyframe_points:
                kp.interpolation = "LINEAR"
    if shot.get("dof"):
        cam.data.dof.use_dof = True
        cam.data.dof.focus_distance = shot["dof"][0]
        cam.data.dof.aperture_fstop = shot["dof"][1]
    else:
        cam.data.dof.use_dof = False


def _fcurves(action):
    try:
        return list(action.fcurves)
    except AttributeError:  # Blender 5 layered actions
        out = []
        for layer in action.layers:
            for strip in layer.strips:
                for cb in strip.channelbags:
                    out += list(cb.fcurves)
        return out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--shot", required=True)
    ap.add_argument("--frames", default=None, help="a:b (inclusive start, exclusive end)")
    ap.add_argument("--still", type=float, default=None, help="render one frame at t in 0..1")
    ap.add_argument("--res", default="1280x720")
    ap.add_argument("--samples", type=int, default=24)
    ap.add_argument("--out", default=os.path.join(BUILD, "frames"))
    ap.add_argument("--blend", default=os.path.join(BUILD, "yonghe.blend"))
    ap.add_argument("--duration", type=float, default=None, help="override shot length (s)")
    ap.add_argument("--tag", default="")
    ap.add_argument("--look", default=None, help="JSON overrides for shot['look']")
    ap.add_argument("--set", default=None, help="JSON overrides for shot keys")
    a = ap.parse_args(argv)

    bpy.ops.wm.open_mainfile(filepath=a.blend)
    sc = bpy.context.scene
    shot = dict(storyboard.get(a.shot))
    if a.look:
        import json
        shot["look"] = {**shot.get("look", {}), **json.loads(a.look)}
    if a.set:
        import json
        shot.update(json.loads(a.set))
    dur = a.duration or storyboard.duration(shot)
    n = max(2, int(round(dur * FPS)))
    apply_shot(sc, shot, n)
    w, h = map(int, a.res.split("x"))
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.cycles.samples = a.samples
    os.makedirs(a.out, exist_ok=True)
    if a.still is not None:
        f = int(round(a.still * (n - 1)))
        sc.frame_set(f)
        sc.render.filepath = os.path.join(a.out, f"{a.shot}_still_{a.still:.2f}{a.tag}.png")
        bpy.ops.render.render(write_still=True)
        return
    f0, f1 = (0, n) if not a.frames else map(int, a.frames.split(":"))
    f1 = min(f1, n)
    for f in range(f0, f1):
        path = os.path.join(a.out, a.shot, f"{f:05d}.png")
        if os.path.exists(path):
            continue
        sc.frame_set(f)
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    main(argv)
