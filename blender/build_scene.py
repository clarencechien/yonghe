"""Build build/yonghe.blend from build/layout.npz.

Everything time-dependent reads the scene property "year", so a shot only
has to animate that one number (plus camera, light and a few look controls).

Run:  python blender/build_scene.py      (with the bpy wheel installed)
"""
import math
import os
import sys

import bpy  # noqa: I001  (must precede bmesh)
import bmesh
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import geo  # noqa: E402
from nodes import NT, drive, driven_value  # noqa: E402

BUILD = os.path.join(HERE, "..", "build")
E = geo.EXTENT

SCENE_PROPS = dict(year=1600.0, bp=0.0, reveal=0.0, ghost=0.0, night=0.0, fog=0.00035,
                   fog_r=0.62, fog_g=0.68, fog_b=0.76, label=0.0)


# ====================================================================== util
def new_obj(name, mesh, coll=None):
    ob = bpy.data.objects.new(name, mesh)
    (coll or bpy.context.scene.collection).objects.link(ob)
    return ob


def bm_to_mesh(bm, name):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me


def box(bm, x0, x1, y0, y1, z0, z1, mat=0):
    vs = [bm.verts.new(v) for v in (
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1))]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    out = []
    for f in faces:
        fc = bm.faces.new([vs[i] for i in f])
        fc.material_index = mat
        out.append(fc)
    return out


def gable(bm, x0, x1, y0, y1, z0, z1, mat=1, over=0.0):
    """Gable roof prism, ridge along x."""
    ym = (y0 + y1) / 2
    x0, x1, y0, y1 = x0 - over, x1 + over, y0 - over, y1 + over
    v = [bm.verts.new(p) for p in (
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, ym, z1), (x1, ym, z1))]
    for f in ((0, 1, 5, 4), (2, 3, 4, 5), (0, 4, 3), (1, 2, 5), (0, 3, 2, 1)):
        fc = bm.faces.new([v[i] for i in f])
        fc.material_index = mat


def set_mats(me, mats):
    for m in mats:
        me.materials.append(m)


def load_layout():
    return np.load(os.path.join(BUILD, "layout.npz"))


# ================================================================ materials
def fog_group(scene):
    """Aerial perspective: blend any shader toward the haze colour by distance."""
    if "Fog" in bpy.data.node_groups:
        return bpy.data.node_groups["Fog"]
    g = bpy.data.node_groups.new("Fog", "ShaderNodeTree")
    g.interface.new_socket("Shader", in_out="INPUT", socket_type="NodeSocketShader")
    g.interface.new_socket("Shader", in_out="OUTPUT", socket_type="NodeSocketShader")
    t = NT(g)
    gi = t.node("NodeGroupInput")
    go = t.node("NodeGroupOutput")
    cam = t.node("ShaderNodeCameraData")
    dens = driven_value(t, scene, "fog")
    f = t.math("EXPONENT", t.mul(t.mul(cam.outputs["View Distance"], dens), -1.0))
    f = t.inv(f)
    col = t.comb(driven_value(t, scene, "fog_r"), driven_value(t, scene, "fog_g"),
                 driven_value(t, scene, "fog_b"))
    em = t.node("ShaderNodeEmission", inputs={"Color": col, "Strength": 1.0})
    # light paths other than camera rays skip the fog
    lp = t.node("ShaderNodeLightPath")
    f = t.mul(f, lp.outputs["Is Camera Ray"])
    mix = t.node("ShaderNodeMixShader", inputs={0: f, 1: gi.outputs[0], 2: em})
    t.set(go.inputs[0], mix)
    return g


def finish(mat, t, shader, scene):
    out = t.node("ShaderNodeOutputMaterial")
    fg = t.node("ShaderNodeGroup")
    fg.node_tree = fog_group(scene)
    t.set(fg.inputs[0], shader)
    t.set(out.inputs["Surface"], fg)


def mat_simple(name, color, scene, rough=0.8, metal=0.0, var=0.12, emit_night=None, palette=None):
    m = bpy.data.materials.new(name)
    t = NT(m.node_tree)
    m.node_tree.nodes.clear()
    oi = t.node("ShaderNodeObjectInfo")
    r = oi.outputs["Random"]
    if palette:
        base = t.ramp(t.math("FRACT", t.mul(r, 7.31)), [(i / len(palette), c) for i, c in enumerate(palette)], "CONSTANT")
    else:
        base = t.rgb(color)
    jitter = t.maprange(r, 0, 1, 1 - var, 1 + var)
    col = t.node("ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY",
                 inputs={0: 1.0, 6: base, 7: t.comb(jitter, jitter, jitter)}).outputs[2]
    bsdf = t.node("ShaderNodeBsdfPrincipled", inputs={"Base Color": col, "Roughness": rough,
                                                      "Metallic": metal})
    if emit_night:
        night = driven_value(t, scene, "night")
        t.set(bsdf.inputs["Emission Color"], t.rgb(emit_night[0]))
        t.set(bsdf.inputs["Emission Strength"], t.mul(night, emit_night[1]))
    finish(m, t, bsdf, scene)
    return m


def mat_facade(name, scene, palette, glass=(0.05, 0.065, 0.075), style="apt"):
    """Procedural facade: floors, window bays, iron window guards, shopfronts,
    weathering streaks, rooftop concrete, lit windows at night."""
    m = bpy.data.materials.new(name)
    m.node_tree.nodes.clear()
    t = NT(m.node_tree)
    tc = t.node("ShaderNodeTexCoord")
    dims = t.node("ShaderNodeAttribute", attribute_type="INSTANCER", attribute_name="dims").outputs["Vector"]
    tint = t.node("ShaderNodeAttribute", attribute_type="INSTANCER", attribute_name="tint").outputs["Fac"]
    o = t.sep(tc.outputs["Object"])
    n = t.sep(tc.outputs["Normal"])
    d = t.sep(dims)
    lx, ly, lz = t.mul(o[0], d[0]), t.mul(o[1], d[1]), t.mul(o[2], d[2])
    xface = t.gt(t.math("ABSOLUTE", n[0]), 0.5)
    u = t.node("ShaderNodeMix", data_type="FLOAT", inputs={0: xface, 2: lx, 3: ly}).outputs[0]
    roof = t.gt(n[2], 0.5)
    fh = 3.2
    bay = 3.4 if style != "tower" else 2.2
    fz = t.math("FRACT", t.math("DIVIDE", lz, fh))
    fu = t.math("FRACT", t.math("DIVIDE", u, bay))
    flo = t.math("FLOOR", t.math("DIVIDE", lz, fh))
    col_i = t.math("FLOOR", t.math("DIVIDE", u, bay))
    cell = t.white(t.comb(flo, col_i, t.mul(tint, 97.0)))
    ground = t.lt(lz, 3.4)
    w_lo, w_hi = (0.30, 0.86) if style != "tower" else (0.12, 0.92)
    win = t.mul(t.mul(t.gt(fz, w_lo), t.lt(fz, w_hi)), t.mul(t.gt(fu, 0.14), t.lt(fu, 0.86)))
    if style == "tower":
        win = t.mul(t.gt(fz, w_lo), t.lt(fz, w_hi))
    win = t.mul(win, t.inv(ground))
    # iron window guards (鐵窗) on walk-ups
    guard = t.mul(t.maxi(t.lt(t.math("FRACT", t.mul(u, 2.4)), 0.14),
                         t.lt(t.math("FRACT", t.mul(lz, 2.2)), 0.16)), win)
    if style in ("tower", "compound"):
        guard = t.mul(guard, 0.0)
    # wall colour from palette, weathering streaks
    wall = t.ramp(tint, [(i / len(palette), c) for i, c in enumerate(palette)], "CONSTANT")
    streak = t.noise(t.comb(t.mul(u, 0.9), t.mul(tint, 50.0), t.mul(lz, 0.06)), 1.0, 3.0, 0.6)
    dirt = t.maprange(streak, 0.35, 0.75, 0.72, 1.05)
    wall = t.node("ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY",
                  inputs={0: 1.0, 6: wall, 7: t.comb(dirt, dirt, dirt)}).outputs[2]
    slab = t.lt(fz, 0.07)
    wall = t.mixc(t.mul(slab, 0.35), wall, t.rgb((0.55, 0.55, 0.53)))
    gl = t.mixc(t.mul(cell, 0.6), t.rgb(glass), t.rgb((glass[0] * 2.2, glass[1] * 2.2, glass[2] * 2.4)))
    c = t.mixc(win, wall, gl)
    c = t.mixc(guard, c, t.rgb((0.32, 0.33, 0.33)))
    # shopfront + signboards on the ground floor
    sign_band = t.mul(ground, t.gt(lz, 2.5))
    sign_col = t.ramp(cell, [(0.0, (0.75, 0.08, 0.06)), (0.2, (0.9, 0.75, 0.1)), (0.4, (0.1, 0.25, 0.65)),
                             (0.6, (0.85, 0.85, 0.82)), (0.8, (0.1, 0.45, 0.25))], "CONSTANT")
    shop = t.mixc(sign_band, t.rgb((0.12, 0.11, 0.1)), sign_col)
    if style in ("compound",):
        shop = wall
    c = t.mixc(ground, c, shop)
    # roof
    rn = t.noise(tc.outputs["Object"], 6.0, 4.0, 0.7)
    roofc = t.mixc(rn, t.rgb((0.36, 0.35, 0.33)), t.rgb((0.5, 0.49, 0.46)))
    c = t.mixc(roof, c, roofc)
    rough = t.node("ShaderNodeMix", data_type="FLOAT", inputs={0: t.mul(win, t.inv(guard)), 2: 0.85, 3: 0.12}).outputs[0]
    # night lights
    night = driven_value(t, scene, "night")
    lit = t.mul(t.mul(win, t.inv(roof)), t.gt(cell, 0.68))
    warm = t.mixc(t.gt(cell, 0.84), t.rgb((1.0, 0.58, 0.26)), t.rgb((0.8, 0.9, 1.0)))
    emis_col = t.mixc(sign_band, warm, sign_col)
    bright = t.maprange(t.math("FRACT", t.mul(cell, 13.7)), 0, 1, 0.25, 1.0)
    emis_str = t.mul(night, t.add(t.mul(t.mul(lit, bright), 0.55), t.mul(t.mul(sign_band, t.inv(roof)), 1.6)))
    bsdf = t.node("ShaderNodeBsdfPrincipled", inputs={"Base Color": c, "Roughness": rough,
                                                      "Emission Color": emis_col,
                                                      "Emission Strength": emis_str})
    finish(m, t, bsdf, scene)
    return m


def mat_ground(scene, imgs):
    m = bpy.data.materials.new("Ground")
    m.node_tree.nodes.clear()
    t = NT(m.node_tree)
    geo_n = t.node("ShaderNodeNewGeometry")
    P = geo_n.outputs["Position"]
    uv = t.vmath("DIVIDE", t.vmath("ADD", P, (E, E, 0)), (2 * E, 2 * E, 1))

    def tex(img, interp="Linear"):
        nd = t.node("ShaderNodeTexImage", interpolation=interp, extension="EXTEND")
        nd.image = img
        t.set(nd.inputs[0], uv)
        rgb = t.sep(nd.outputs["Color"])
        return rgb[0], rgb[1], rgb[2], nd.outputs["Alpha"]

    road, ryear, dirt, water = tex(imgs["roads"])
    pid, track, bank, creek = tex(imgs["zone"], "Closest")
    plan, order, ghost, pfill = tex(imgs["plan"])
    gyear, zone, _, _ = tex(imgs["gyear"])

    Y = driven_value(t, scene, "year")
    yn = t.math("DIVIDE", t.sub(Y, 1600.0), 500.0)
    wpos = t.vmath("SCALE", P, (0, 0, 0))
    n1 = t.noise(P, 0.004, 4.0, 0.6)
    n2 = t.noise(P, 0.03, 3.0, 0.55)
    n3 = t.noise(P, 0.25, 2.0, 0.5)

    # wild land
    wild = t.mixc(n1, t.rgb((0.03, 0.065, 0.015)), t.rgb((0.075, 0.115, 0.03)))
    wild = t.mixc(t.mul(n3, 0.35), wild, t.rgb((0.12, 0.12, 0.06)))
    # paddy fields: voronoi plots with varied crop states and flooded plots
    vor = t.node("ShaderNodeTexVoronoi", inputs={"Scale": 0.028, "Randomness": 0.35})
    t.set(vor.inputs["Vector"], t.vmath("MULTIPLY", P, (1.0, 1.6, 1.0)))
    cellc = vor.outputs["Color"]
    cr = t.sep(cellc)[0]
    crop = t.ramp(cr, [(0.0, (0.07, 0.17, 0.03)), (0.3, (0.11, 0.22, 0.04)),
                       (0.55, (0.18, 0.24, 0.06)), (0.72, (0.26, 0.25, 0.09)), (0.85, (0.08, 0.11, 0.09)),
                       (0.93, (0.15, 0.17, 0.15))])
    crop = t.mixc(t.mul(n3, 0.25), crop, t.rgb((0.12, 0.18, 0.06)))
    edge = t.lt(vor.outputs["Distance"], 0.06)
    vor2 = t.node("ShaderNodeTexVoronoi", feature="DISTANCE_TO_EDGE", inputs={"Scale": 0.028, "Randomness": 0.35})
    t.set(vor2.inputs["Vector"], t.vmath("MULTIPLY", P, (1.0, 1.6, 1.0)))
    bund = t.lt(vor2.outputs["Distance"], 0.035)
    fields = t.mixc(bund, crop, t.rgb((0.17, 0.16, 0.09)))
    farm_on = t.mul(t.smooth(Y, 1700.0, 1820.0), t.gt(t.add(n1, t.maprange(Y, 1700, 1820, -0.6, 0.6)), 0.5))
    farm_on = t.mul(farm_on, t.lt(Y, 3000.0))
    gcol = t.mixc(farm_on, wild, fields)
    # dirt paths
    gcol = t.mixc(t.mul(t.mul(dirt, t.smooth(Y, 1720.0, 1760.0)), 0.9), gcol, t.rgb((0.36, 0.30, 0.20)))
    # urban hardstanding
    urb = t.smooth(yn, t.sub(gyear, 0.004), gyear)
    urbcol = t.mixc(n2, t.rgb((0.15, 0.145, 0.135)), t.rgb((0.24, 0.23, 0.21)))
    gcol = t.mixc(urb, gcol, urbcol)
    # parks (planned 1955): open green until converted
    park_alive = t.node("ShaderNodeValue")
    alive = None
    pid8 = t.mul(pid, 8.0)
    for i, (pidn, c, r, fate, conv, keep) in enumerate(geo.PARKS):
        is_i = t.lt(t.math("ABSOLUTE", t.sub(pid8, float(i + 1))), 0.5)
        if conv is None:
            a = 1.0
            ai = is_i
        else:
            a = t.inv(t.smooth(Y, float(conv), float(conv) + 1.5))
            if fate == "renai":
                # western part survives
                west = t.lt(t.sub(t.sep(P)[0], c[0]), -r + 2 * r * keep)
                a = t.maxi(a, west)
            ai = t.mul(is_i, a)
        alive = ai if alive is None else t.add(alive, ai)
    park_on = t.mul(t.mul(alive, t.smooth(Y, 1955.5, 1957.0)), 1.0)
    grass = t.mixc(n2, t.rgb((0.13, 0.25, 0.07)), t.rgb((0.22, 0.32, 0.10)))
    gcol = t.mixc(park_on, gcol, grass)
    # school sports grounds once parks 2 and 5 become schools
    school_t = t.smooth(Y, 1968.0, 1970.0)
    tr = t.mul(t.gt(track, 0.75), school_t)
    infield = t.mul(t.mul(t.gt(track, 0.25), t.lt(track, 0.75)), school_t)
    gcol = t.mixc(tr, gcol, t.rgb((0.42, 0.16, 0.10)))
    gcol = t.mixc(infield, gcol, t.rgb((0.20, 0.30, 0.10)))
    # roads
    road_on = t.mul(road, t.smooth(yn, t.sub(ryear, 0.002), t.add(ryear, 0.002)))
    asphalt = t.mixc(n2, t.rgb((0.07, 0.07, 0.075)), t.rgb((0.11, 0.11, 0.11)))
    gcol = t.mixc(road_on, gcol, asphalt)
    # river banks (floodplain grass / gravel), creek
    bankc = t.mixc(n2, t.rgb((0.09, 0.12, 0.05)), t.rgb((0.20, 0.19, 0.13)))
    gcol = t.mixc(t.mul(bank, t.inv(water)), gcol, bankc)
    gcol = t.mixc(water, gcol, t.rgb((0.10, 0.09, 0.07)))
    gcol = t.mixc(creek, gcol, t.rgb((0.05, 0.07, 0.06)))

    # 1955 blueprint overlay
    bp = driven_value(t, scene, "bp")
    reveal = driven_value(t, scene, "reveal")
    shown = t.mul(plan, t.lt(order, reveal))
    gray = t.node("ShaderNodeRGBToBW", inputs={0: gcol}).outputs[0]
    g2 = t.mul(gray, 0.35)
    bpbg = t.mixc(0.8, t.comb(g2, g2, g2), t.rgb((0.012, 0.03, 0.07)))
    gcol = t.mixc(bp, gcol, bpbg)
    ghost_v = driven_value(t, scene, "ghost")
    em_fill = t.mul(t.mul(t.mul(pfill, t.lt(order, reveal)), bp), 0.35)
    em_str = t.add(t.add(t.mul(t.mul(shown, bp), 5.0), em_fill), t.mul(t.add(t.mul(ghost, 1.0), t.mul(pfill, 0.12)), t.mul(ghost_v, 5.0)))
    em_col = t.mixc(t.gt(ghost_v, 0.01), t.rgb((0.35, 0.75, 1.0)), t.rgb((0.45, 1.0, 0.55)))
    # street lights at night
    night = driven_value(t, scene, "night")
    em_str = t.add(em_str, t.mul(t.mul(road_on, night), 0.9))
    em_col = t.mixc(t.mul(t.mul(road_on, night), t.inv(t.gt(em_str, 1.0))), em_col, t.rgb((1.0, 0.62, 0.3)))
    bsdf = t.node("ShaderNodeBsdfPrincipled", inputs={"Base Color": gcol, "Roughness": 0.92,
                                                      "Emission Color": em_col, "Emission Strength": em_str})
    finish(m, t, bsdf, scene)
    return m


def mat_outskirts(scene):
    m = bpy.data.materials.new("outskirts")
    t = NT(m.node_tree)
    m.node_tree.nodes.clear()
    tc = t.node("ShaderNodeTexCoord")
    n = t.node("ShaderNodeTexNoise", inputs={"Scale": 0.004, "Detail": 6.0, "Roughness": 0.65})
    t.set(n.inputs["Vector"], tc.outputs["Object"])
    city = t.ramp(n.outputs["Fac"], [(0.35, (0.16, 0.16, 0.15, 1)), (0.5, (0.30, 0.29, 0.27, 1)),
                                      (0.62, (0.20, 0.24, 0.15, 1))])
    farm = t.ramp(n.outputs["Fac"], [(0.35, (0.10, 0.14, 0.05, 1)), (0.5, (0.17, 0.20, 0.08, 1)),
                                      (0.62, (0.13, 0.17, 0.07, 1))])
    # farmland around Taipei until the post-war boom, city afterwards
    urban = t.maprange(driven_value(t, scene, "year"), 1945.0, 1985.0, 0.0, 1.0)
    col = t.mixc(urban, farm, city)
    bsdf = t.node("ShaderNodeBsdfPrincipled", inputs={"Base Color": col, "Roughness": 0.9})
    v = t.node("ShaderNodeTexVoronoi", inputs={"Scale": 0.03, "Randomness": 1.0})
    t.set(v.inputs["Vector"], tc.outputs["Object"])
    sp = t.maprange(v.outputs["Distance"], 0.0, 0.18, 1.0, 0.0)
    t.set(bsdf.inputs["Emission Color"], t.rgb((1.0, 0.72, 0.42)))
    t.set(bsdf.inputs["Emission Strength"], t.mul(t.mul(t.mul(sp, urban), driven_value(t, scene, "night")), 3.0))
    finish(m, t, bsdf, scene)
    return m


def mat_water(scene):
    m = bpy.data.materials.new("Water")
    m.node_tree.nodes.clear()
    t = NT(m.node_tree)
    P = t.node("ShaderNodeNewGeometry").outputs["Position"]
    nz = t.noise(t.vmath("MULTIPLY", P, (1.0, 1.0, 1.0)), 0.08, 6.0, 0.6)
    bump = t.node("ShaderNodeBump", inputs={"Strength": 0.08, "Height": nz})
    col = t.mixc(t.noise(P, 0.003, 2.0, 0.5), t.rgb((0.04, 0.07, 0.06)), t.rgb((0.07, 0.09, 0.07)))
    bsdf = t.node("ShaderNodeBsdfPrincipled", inputs={"Base Color": col, "Roughness": 0.06,
                                                      "Normal": bump.outputs[0], "IOR": 1.33})
    finish(m, t, bsdf, scene)
    return m


# =================================================================== assets
def make_assets(scene, coll):
    A = {}
    M = {}
    M["roof_tile_red"] = mat_simple("RoofRed", (0.42, 0.14, 0.08), scene, 0.75)
    M["roof_gray"] = mat_simple("RoofGray", (0.17, 0.17, 0.18), scene, 0.8, var=0.25)
    M["roof_dachen"] = mat_simple("RoofDachen", (0.22, 0.22, 0.23), scene, 0.8, var=0.15)
    M["wall_white"] = mat_simple("WallWhite", (0.62, 0.6, 0.55), scene, 0.9, var=0.15,
                                 emit_night=((1.0, 0.7, 0.4), 0.15))
    M["wall_brick"] = mat_simple("WallBrick", (0.45, 0.22, 0.14), scene, 0.9)
    M["court"] = mat_simple("Courtyard", (0.42, 0.30, 0.22), scene, 0.95)
    M["thatch"] = mat_simple("Thatch", (0.40, 0.32, 0.17), scene, 0.95)
    M["bamboo"] = mat_simple("Wood", (0.30, 0.22, 0.13), scene, 0.9)
    M["leaf"] = mat_simple("Leaf", (0.07, 0.15, 0.04), scene, 0.85, var=0.35)
    M["trunk"] = mat_simple("Trunk", (0.12, 0.09, 0.06), scene, 0.9)
    M["steel"] = mat_simple("Steel", (0.72, 0.72, 0.7), scene, 0.35, metal=0.9, var=0.05)
    M["sheet"] = mat_simple("Sheet", (0.18, 0.33, 0.52), scene, 0.55, var=0.25, palette=[
        (0.16, 0.24, 0.34), (0.30, 0.32, 0.33), (0.20, 0.30, 0.38), (0.26, 0.17, 0.12),
        (0.36, 0.37, 0.36), (0.17, 0.25, 0.20), (0.40, 0.40, 0.38)])
    M["concrete"] = mat_simple("Concrete", (0.5, 0.49, 0.46), scene, 0.85, var=0.05)
    M["concrete_old"] = mat_simple("ConcreteOld", (0.42, 0.40, 0.36), scene, 0.9, var=0.05)
    M["boat"] = mat_simple("Boat", (0.22, 0.15, 0.09), scene, 0.8)
    M["apt"] = mat_facade("FacadeApt", scene, [(0.44, 0.38, 0.30), (0.52, 0.50, 0.45), (0.34, 0.24, 0.18),
                                               (0.47, 0.41, 0.34), (0.40, 0.40, 0.38), (0.46, 0.34, 0.30),
                                               (0.36, 0.39, 0.35), (0.56, 0.54, 0.50), (0.30, 0.28, 0.26),
                                               (0.50, 0.44, 0.36)])
    M["mid"] = mat_facade("FacadeMid", scene, [(0.50, 0.46, 0.40), (0.40, 0.38, 0.35), (0.58, 0.56, 0.52),
                                               (0.33, 0.29, 0.26), (0.46, 0.46, 0.44), (0.42, 0.33, 0.27)], style="mid")
    M["tower"] = mat_facade("FacadeTower", scene, [(0.50, 0.50, 0.48), (0.36, 0.38, 0.39), (0.58, 0.56, 0.52),
                                                   (0.28, 0.30, 0.32)], glass=(0.05, 0.065, 0.08), style="tower")
    M["compound"] = mat_facade("FacadeSchool", scene, [(0.74, 0.70, 0.58), (0.70, 0.62, 0.50)], style="compound")

    def asset(name, bm, mats):
        me = bm_to_mesh(bm, name)
        set_mats(me, mats)
        for p in me.polygons:
            p.use_smooth = False
        ob = new_obj("A_" + name, me, coll)
        A[name] = ob
        return ob

    # unit box with pivot at bottom centre (facade-shaded)
    for nm in ("apt", "mid", "tower", "compound"):
        bm = bmesh.new()
        box(bm, -0.5, 0.5, -0.5, 0.5, 0, 0.97)
        e = 0.025
        for x0, x1, y0, y1 in ((-0.5, 0.5, -0.5, -0.5 + e), (-0.5, 0.5, 0.5 - e, 0.5),
                               (-0.5, -0.5 + e, -0.5, 0.5), (0.5 - e, 0.5, -0.5, 0.5)):
            box(bm, x0, x1, y0, y1, 0.97, 1.0)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        asset(nm, bm, [M[nm]])
    # parapet-less rooftop shed (頂樓加蓋): unit box + sloped sheet roof
    bm = bmesh.new()
    box(bm, -0.5, 0.5, -0.5, 0.5, 0, 0.8, 0)
    gable(bm, -0.5, 0.5, -0.5, 0.5, 0.8, 1.0, 1, over=0.04)
    asset("shed", bm, [M["wall_white"], M["sheet"]])
    # stainless water tank on a stand
    bm = bmesh.new()
    box(bm, -0.8, 0.8, -0.8, 0.8, 0, 0.5, 1)
    r = bmesh.ops.create_cone(bm, cap_ends=True, segments=10, radius1=0.75, radius2=0.75, depth=1.5)
    bmesh.ops.translate(bm, verts=r["verts"], vec=(0, 0, 1.25))
    asset("tank", bm, [M["steel"], M["concrete"]])
    # 平房: walls + grey tile gable roof (unit)
    bm = bmesh.new()
    box(bm, -0.5, 0.5, -0.5, 0.5, 0, 0.72, 0)
    gable(bm, -0.5, 0.5, -0.5, 0.5, 0.72, 1.0, 1, over=0.06)
    asset("pinfang", bm, [M["wall_white"], M["roof_gray"]])
    bm = bmesh.new()
    box(bm, -0.5, 0.5, -0.5, 0.5, 0, 0.75, 0)
    gable(bm, -0.5, 0.5, -0.5, 0.5, 0.75, 1.0, 1, over=0.05)
    asset("dachen", bm, [M["wall_white"], M["roof_dachen"]])
    bm = bmesh.new()
    box(bm, -0.5, 0.5, -0.5, 0.5, 0, 1.0, 0)
    asset("dachen_add", bm, [M["sheet"]])
    # 三合院 farmhouse in metres (unit scale = 1)
    bm = bmesh.new()
    box(bm, -9, 9, 4, 11, 0, 3.4, 0)
    gable(bm, -9, 9, 4, 11, 3.4, 5.6, 1, over=0.6)
    for sx in (-1, 1):
        x0, x1 = sorted((sx * 9, sx * 3))
        box(bm, x0, x1, -10, 4, 0, 3.0, 0)
        bm2 = bmesh.new()
        gable(bm2, -7, 7, -3, 3, 0, 1.8, 1, over=0.5)
        bmesh.ops.rotate(bm2, verts=bm2.verts, matrix=__import__("mathutils").Matrix.Rotation(math.pi / 2, 3, "Z"))
        bmesh.ops.translate(bm2, verts=bm2.verts, vec=((x0 + x1) / 2, -3, 3.0))
        tmp = bpy.data.meshes.new("tmp")
        bm2.to_mesh(tmp)
        bm2.free()
        bm.from_mesh(tmp)
        bpy.data.meshes.remove(tmp)
    v = [bm.verts.new(p) for p in ((-3, -10, 0.05), (3, -10, 0.05), (3, 4, 0.05), (-3, 4, 0.05))]
    bm.faces.new(v).material_index = 2
    asset("farm", bm, [M["wall_brick"], M["roof_tile_red"], M["court"]])
    # thatched hut (unit)
    bm = bmesh.new()
    r = bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.5, radius2=0.5, depth=0.45)
    bmesh.ops.translate(bm, verts=r["verts"], vec=(0, 0, 0.225))
    for f in bm.faces:
        f.material_index = 0
    r = bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.62, radius2=0.0, depth=0.6)
    bmesh.ops.translate(bm, verts=r["verts"], vec=(0, 0, 0.75))
    for f in bm.faces:
        if f.calc_center_median().z > 0.46:
            f.material_index = 1
    asset("hut", bm, [M["bamboo"], M["thatch"]])
    # low-poly tree (crown ~7 m), rough vertex jitter for variety
    bm = bmesh.new()
    r = bmesh.ops.create_icosphere(bm, subdivisions=2, radius=3.6)
    rng = np.random.default_rng(3)
    for vv in r["verts"]:
        vv.co *= 1 + rng.uniform(-0.15, 0.15)
        vv.co.z *= 0.85
        vv.co.z += 5.2
    for f in bm.faces:
        f.material_index = 0
    r = bmesh.ops.create_cone(bm, cap_ends=True, segments=5, radius1=0.35, radius2=0.25, depth=3.0)
    bmesh.ops.translate(bm, verts=r["verts"], vec=(0, 0, 1.5))
    for vv in r["verts"]:
        for f in vv.link_faces:
            f.material_index = 1
    asset("tree", bm, [M["leaf"], M["trunk"]])
    # sampan
    bm = bmesh.new()
    box(bm, -4, 4, -1, 1, -0.3, 0.5, 0)
    box(bm, -1, 1.5, -0.9, 0.9, 0.5, 1.6, 0)
    asset("boat", bm, [M["boat"]])

    # bridges (local +x from Yonghe foot to Taipei foot)
    def bridge(name, width, length, arch=False, mat="concrete_old"):
        bm = bmesh.new()
        hw = width / 2
        box(bm, -40, length + 40, -hw, hw, 5.0, 6.2, 0)
        for s in (-1, 1):
            box(bm, -40, length + 40, s * hw - 0.25 * (s + 1), s * hw - 0.25 * (s - 1), 6.2, 7.2, 0)
        step = 30.0 if arch else 45.0
        for x in np.arange(0, length + 1, step):
            if arch:
                for s in (-1, 1):
                    yc = s * (hw - 1.0)
                    box(bm, x - 0.8, x + 0.8, yc - 0.6, yc + 0.6, -6, 5.0, 0)
                box(bm, x - 0.8, x + 0.8, -hw + 0.4, hw - 0.4, 3.6, 5.0, 0)
                # shallow arch soffit between piers, faceted
                for k in range(6):
                    a0, a1 = k / 6, (k + 1) / 6
                    xa, xb = x + 0.8 + a0 * (step - 1.6), x + 0.8 + a1 * (step - 1.6)
                    za = 5.0 - 1.6 * math.sin(math.pi * (a0 + a1) / 2)
                    box(bm, xa, xb, -hw + 0.2, hw - 0.2, za, 5.0, 0)
            else:
                box(bm, x - 1.2, x + 1.2, -hw * 0.7, hw * 0.7, -6, 5.0, 0)
        return asset(name, bm, [M[mat]])

    L = math.dist(geo.BRIDGE_A, geo.BRIDGE_B)
    bridge("bridge1937", 5.3, L, arch=True)
    bridge("bridge1961", 15.4, L + 100, arch=False)
    bridge("bridge1972", 24.3, L + 100, arch=False, mat="concrete")
    bridge("bridge_modern", 22.0, 560, mat="concrete")

    # embankment (堤防) along both river banks, absolute coordinates
    bm = bmesh.new()
    pts = np.array(geo.RIVER, float)
    dense = []
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        for t_ in np.linspace(0, 1, 20, endpoint=False):
            dense.append((x0 + (x1 - x0) * t_, y0 + (y1 - y0) * t_))
    dense.append(tuple(pts[-1]))
    dense = np.array(dense)
    from scipy.ndimage import gaussian_filter1d
    dense = np.c_[gaussian_filter1d(dense[:, 0], 6, mode="nearest"), gaussian_filter1d(dense[:, 1], 6, mode="nearest")]
    tang = np.gradient(dense, axis=0)
    tang /= np.linalg.norm(tang, axis=1)[:, None]
    nrm = np.c_[-tang[:, 1], tang[:, 0]]
    for side in (-1, 1):
        off = geo.RIVER_HALF_WIDTH + geo.FLOODPLAIN + 4
        prof = [(-6, 0), (-2.5, 6.5), (2.5, 6.5), (6, 0)]
        rows = []
        for p, nv in zip(dense, nrm):
            c = p + side * nv * off
            rows.append([bm.verts.new((c[0] + nv[0] * a, c[1] + nv[1] * a, z)) for a, z in prof])
        for r0, r1 in zip(rows[:-1], rows[1:]):
            for k in range(3):
                f = bm.faces.new((r0[k], r0[k + 1], r1[k + 1], r1[k]))
                f.material_index = 0
    asset("levee", bm, [M["concrete"]])
    return A, M


# ============================================================ GN systems
def timed_gn(scene, name, inst, mode="Z", extras=None):
    """Geometry nodes: instance `inst` on points, scaled by the timeline.

    Point attributes: birth, death, w, d, h, rot, tint.
    mode Z: rise from the ground (buildings); U: uniform growth (trees);
    X: extend along local x (bridges); S: fixed scale (no growth, pop in).
    """
    ng = bpy.data.node_groups.new("GN_" + name, "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    t = NT(ng)
    gi = t.node("NodeGroupInput")
    go = t.node("NodeGroupOutput")

    def attr(nm, vec=False):
        nd = t.node("GeometryNodeInputNamedAttribute", data_type="FLOAT_VECTOR" if vec else "FLOAT")
        nd.inputs["Name"].default_value = nm
        return nd.outputs["Attribute"]

    year = t.node("ShaderNodeValue")
    drive(year.outputs[0], "default_value", scene, "year")
    Y = year.outputs[0]
    birth, death = attr("birth"), attr("death")
    dur = {"Z": 1.2, "U": 3.0, "X": 1.5, "S": 0.05}[mode]
    g_in = t.smooth(Y, birth, t.add(birth, dur))
    g_out = t.inv(t.smooth(Y, death, t.add(death, 0.6)))
    grow = t.mul(g_in, g_out)
    pts = t.node("GeometryNodeMeshToPoints", inputs={"Mesh": gi.outputs[0]})
    dele = t.node("GeometryNodeDeleteGeometry", domain="POINT",
                  inputs={"Geometry": pts.outputs[0], "Selection": t.lt(grow, 0.001)})
    w, d, h, rot, tint = attr("w"), attr("d"), attr("h"), attr("rot"), attr("tint")
    if mode == "Z":
        scale = t.comb(w, d, t.mul(h, grow))
    elif mode == "U":
        s = t.mul(w, grow)
        scale = t.comb(s, s, s)
    elif mode == "X":
        scale = t.comb(t.mul(w, grow), d, h)
    else:
        scale = t.comb(w, d, h)
    oi = t.node("GeometryNodeObjectInfo", transform_space="ORIGINAL")
    oi.inputs["Object"].default_value = inst
    oi.inputs["As Instance"].default_value = True
    iop = t.node("GeometryNodeInstanceOnPoints", inputs={
        "Points": dele.outputs[0], "Instance": oi.outputs["Geometry"],
        "Rotation": t.comb(0.0, 0.0, rot), "Scale": scale})
    st1 = t.node("GeometryNodeStoreNamedAttribute", data_type="FLOAT_VECTOR", domain="INSTANCE",
                 inputs={"Geometry": iop.outputs[0], "Name": "dims", "Value": t.comb(w, d, h)})
    st2 = t.node("GeometryNodeStoreNamedAttribute", data_type="FLOAT", domain="INSTANCE",
                 inputs={"Geometry": st1.outputs[0], "Name": "tint", "Value": tint})
    join = t.node("GeometryNodeJoinGeometry")
    t.links.new(st2.outputs[0], join.inputs[0])

    # rooftop clutter: water tanks and sheet-metal sheds on walk-ups
    for ex_obj, prob_lo, prob_hi, fixed, off in (extras or []):
        sel_r = t.mul(t.gt(tint, prob_lo), t.lt(tint, prob_hi))
        roof_ok = t.gt(g_in, 0.98)
        keep = t.mul(sel_r, roof_ok)
        d2 = t.node("GeometryNodeDeleteGeometry", domain="POINT",
                    inputs={"Geometry": dele.outputs[0], "Selection": t.lt(keep, 0.5)})
        # offset in the building's local frame
        offv = t.comb(t.mul(w, off[0]), t.mul(d, off[1]), 0.0)
        vr = t.node("ShaderNodeVectorRotate", rotation_type="Z_AXIS", inputs={"Vector": offv, "Angle": rot})
        pos = t.node("GeometryNodeInputPosition")
        newp = t.vmath("ADD", t.vmath("ADD", pos.outputs[0], vr.outputs[0]), t.comb(0.0, 0.0, t.mul(h, grow)))
        sp = t.node("GeometryNodeSetPosition", inputs={"Geometry": d2.outputs[0], "Position": newp})
        oi2 = t.node("GeometryNodeObjectInfo", transform_space="ORIGINAL")
        oi2.inputs["Object"].default_value = ex_obj
        oi2.inputs["As Instance"].default_value = True
        if fixed == "shed":
            sc = t.comb(t.mul(w, 0.62), t.mul(d, 0.5), 2.9)
        else:
            sc = (1.0, 1.0, 1.0)
        iop2 = t.node("GeometryNodeInstanceOnPoints", inputs={
            "Points": sp.outputs[0], "Instance": oi2.outputs["Geometry"],
            "Rotation": t.comb(0.0, 0.0, rot), "Scale": sc})
        t.links.new(iop2.outputs[0], join.inputs[0])
    t.links.new(join.outputs[0], go.inputs[0])
    return ng


def points_object(name, data, coll):
    n = len(data["x"])
    me = bpy.data.meshes.new(name)
    me.vertices.add(n)
    co = np.zeros((n, 3), np.float32)
    co[:, 0] = data["x"]
    co[:, 1] = data["y"]
    me.vertices.foreach_set("co", co.ravel())
    for k in ("birth", "death", "w", "d", "h", "rot", "tint"):
        a = me.attributes.new(k, "FLOAT", "POINT")
        a.data.foreach_set("value", np.asarray(data[k], np.float32))
    me.update()
    return new_obj(name, me, coll)


# ================================================================== images
def make_image(name, rgba, path):
    h, w, _ = rgba.shape
    img = bpy.data.images.new(name, w, h, alpha=True, float_buffer=True)
    img.pixels.foreach_set(np.ascontiguousarray(rgba[::-1]).astype(np.float32).ravel())
    img.filepath_raw = path
    img.file_format = "OPEN_EXR"
    img.save()
    img.source = "FILE"
    img.colorspace_settings.name = "Non-Color"
    img.reload()
    return img


# ==================================================================== main
def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    for k, v in SCENE_PROPS.items():
        sc[k] = v
    L = load_layout()
    f32 = lambda k: L[k].astype(np.float32)  # noqa: E731

    print("images")
    imgs = {
        "roads": make_image("roads", np.dstack([f32("roads"), f32("ryear"), f32("dirt"), f32("water")]),
                            os.path.join(BUILD, "tex_roads.exr")),
        "zone": make_image("zone", np.dstack([f32("pid") / 8.0, f32("track"), f32("bank"), f32("creek")]),
                           os.path.join(BUILD, "tex_zone.exr")),
        "plan": make_image("plan", np.dstack([f32("plan"), f32("order"), f32("ghost"), f32("pfill")]),
                           os.path.join(BUILD, "tex_plan.exr")),
        "gyear": make_image("gyear", np.dstack([f32("gyear"), np.zeros_like(f32("gyear")),
                                                np.zeros_like(f32("gyear")), np.ones_like(f32("gyear"))]),
                            os.path.join(BUILD, "tex_gyear.exr")),
    }
    # park id: recode surviving west part of park 1 handled in shader

    print("terrain")
    res = 720
    xs = np.linspace(-E, E, res)
    X, Yg = np.meshgrid(xs, xs)
    water = f32("water")[::-1]  # flip to south-up rows
    # sample water at vertices
    iu = np.clip(((X + E) / (2 * E) * (geo.TEX - 1)).astype(int), 0, geo.TEX - 1)
    iv = np.clip(((Yg + E) / (2 * E) * (geo.TEX - 1)).astype(int), 0, geo.TEX - 1)
    dr = f32("d_river")[::-1][iv, iu]
    zz = -np.clip((geo.RIVER_HALF_WIDTH + 8 - dr) / 25, 0, 1) * 7.0
    rng = np.random.default_rng(7)
    zz += (rng.random(zz.shape) - 0.5) * 0.15
    me = bpy.data.meshes.new("terrain")
    verts = np.c_[X.ravel(), Yg.ravel(), zz.ravel()].astype(np.float32)
    idx = np.arange(res * res).reshape(res, res)
    quads = np.stack([idx[:-1, :-1], idx[:-1, 1:], idx[1:, 1:], idx[1:, :-1]], -1).reshape(-1, 4)
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.ravel())
    me.loops.add(quads.size)
    me.loops.foreach_set("vertex_index", quads.ravel())
    me.polygons.add(len(quads))
    me.polygons.foreach_set("loop_start", np.arange(0, quads.size, 4))
    me.update(calc_edges=True)
    me.validate()
    terrain = new_obj("Terrain", me)
    terrain.data.materials.append(mat_ground(sc, imgs))
    bpy.ops.mesh.primitive_plane_add(size=2 * E)
    wp = bpy.context.active_object
    wp.name = "Water"
    wp.location.z = -2.2
    wp.data.materials.append(mat_water(sc))

    # Beyond the modelled square: a 60 km plain of mottled city, mostly
    # swallowed by haze, so wide shots never show the end of the world.
    bpy.ops.mesh.primitive_plane_add(size=60000)
    outer = bpy.context.active_object
    outer.name = "Outskirts"
    outer.location.z = -3.0
    outer.data.materials.append(mat_outskirts(sc))

    print("assets")
    lib = bpy.data.collections.new("Assets")
    sc.collection.children.link(lib)
    A, M = make_assets(sc, lib)
    lib.hide_render = True
    lib.hide_viewport = True

    print("systems")
    city = bpy.data.collections.new("City")
    sc.collection.children.link(city)
    roof_extras = [(A["tank"], 0.0, 0.72, "tank", (0.22, -0.18)),
                   (A["shed"], 0.35, 0.80, "shed", (-0.12, 0.15))]
    specs = [
        ("pinfang", "pinfang", "Z", None), ("apt", "apt", "Z", roof_extras),
        ("mid", "mid", "Z", [roof_extras[0]]), ("tower", "tower", "Z", None),
        ("farm", "farm", "S", None), ("hut", "hut", "S", None), ("dachen", "dachen", "Z", None),
        ("dachen_add", "dachen_add", "Z", None), ("compound", "compound", "Z", None),
        ("tree", "tree", "U", None),
    ]
    for cat, asset, mode, ex in specs:
        data = {k: L[f"{cat}__{k}"] for k in ("x", "y", "birth", "death", "w", "d", "h", "rot", "tint")}
        ob = points_object("SYS_" + cat, data, city)
        mod = ob.modifiers.new("timeline", "NODES")
        mod.node_group = timed_gn(sc, cat, A[asset], mode, ex)

    # bridges, levee, boat as single-point systems
    def single(name, asset, x, y, rot, birth, death, mode, w=1.0, d=1.0, h=1.0):
        data = dict(x=[x], y=[y], birth=[birth], death=[death], w=[w], d=[d], h=[h], rot=[rot], tint=[0.5])
        ob = points_object("SYS_" + name, data, city)
        mod = ob.modifiers.new("timeline", "NODES")
        mod.node_group = timed_gn(sc, name, A[asset], mode)
        return ob

    ax, ay = geo.BRIDGE_A
    bx, by = geo.BRIDGE_B
    rot = math.atan2(by - ay, bx - ax)
    single("bridge1937", "bridge1937", ax, ay, rot, 1936.0, 1961.0, "X")
    single("bridge1961", "bridge1961", ax - 50 * math.cos(rot), ay - 50 * math.sin(rot), rot, 1961.0, 1972.0, "S")
    single("bridge1972", "bridge1972", ax - 50 * math.cos(rot), ay - 50 * math.sin(rot), rot, 1972.0, 9999.0, "S")
    for nm, (a, b), yr in (("yongfu", (geo.YONGFU_A, geo.YONGFU_B), 1990.0),
                           ("fuhe", (geo.FUHE_A, geo.FUHE_B), 1990.0),
                           ("xiulang", (geo.XIULANG_A, geo.XIULANG_B), 1990.0)):
        r_ = math.atan2(b[1] - a[1], b[0] - a[0])
        L_ = math.dist(a, b)
        single(nm, "bridge_modern", a[0] - (560 - L_) / 2 * math.cos(r_), a[1] - (560 - L_) / 2 * math.sin(r_),
               r_, yr, 9999.0, "S")
    single("levee", "levee", 0.0, 0.0, 0.0, 1962.0, 9999.0, "Z")
    boat = single("boat", "boat", 0.0, 0.0, 0.0, 1700.0, 1937.0, "S")
    boat.location = (*geo.FERRY_A, -1.9)

    print("world")
    w = bpy.data.worlds.new("World")
    sc.world = w
    t = NT(w.node_tree)
    w.node_tree.nodes.clear()
    sky = t.node("ShaderNodeTexSky", sky_type="MULTIPLE_SCATTERING")
    sky.sun_elevation = math.radians(35)
    sky.sun_rotation = math.radians(200)
    sky.altitude = 200
    sky.aerosol_density = 3.0
    bg = t.node("ShaderNodeBackground", inputs={"Color": sky.outputs[0], "Strength": 0.25})
    # Seen by the camera, the sky fades into the haze colour toward the
    # horizon so the far edge of the model dissolves instead of cutting off.
    tc = t.node("ShaderNodeTexCoord")
    dz = t.node("ShaderNodeSeparateXYZ")
    t.set(dz.inputs[0], tc.outputs["Generated"])
    hz = t.inv(t.maprange(dz.outputs["Z"], -0.02, 0.32, 0.0, 1.0))
    hz = t.mul(t.mul(hz, hz), t.node("ShaderNodeLightPath").outputs["Is Camera Ray"])
    fogc = t.comb(driven_value(t, sc, "fog_r"), driven_value(t, sc, "fog_g"), driven_value(t, sc, "fog_b"))
    haze = t.node("ShaderNodeBackground", inputs={"Color": fogc, "Strength": 1.0})
    mixw = t.node("ShaderNodeMixShader", inputs={0: hz, 1: bg, 2: haze})
    out = t.node("ShaderNodeOutputWorld")
    t.set(out.inputs[0], mixw)
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sc.collection.objects.link(sun)
    sun.data.energy = 4.0
    sun.data.angle = math.radians(1.5)
    sun.data.color = (1.0, 0.95, 0.88)

    cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    sc.collection.objects.link(cam)
    cam.data.clip_start = 1.0
    cam.data.clip_end = 20000
    cam.data.sensor_width = 36
    sc.camera = cam

    r = sc.render
    r.engine = "CYCLES"
    r.resolution_x, r.resolution_y = 1280, 720
    r.fps = 24
    r.use_persistent_data = True
    r.image_settings.file_format = "PNG"
    cy = sc.cycles
    cy.device = "CPU"
    cy.samples = 24
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = 0.05
    cy.use_denoising = True
    cy.max_bounces = 4
    cy.diffuse_bounces = 2
    cy.glossy_bounces = 2
    cy.transmission_bounces = 0
    cy.volume_bounces = 0
    cy.transparent_max_bounces = 2
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    cy.blur_glossy = 1.0
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass

    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(BUILD, "yonghe.blend"))
    print("saved")


if __name__ == "__main__":
    main()
