"""Generate the ground masks and building sites for the Yonghe model.

Pure numpy/scipy; writes build/layout.npz, which build_scene.py turns into
textures and geometry-node point clouds.

Every building site carries a timeline (birth/death years), so a single
"year" value in Blender drives the whole city from 1600 to 2024.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.dirname(__file__))
import geo  # noqa: E402

RNG = np.random.default_rng(1955)
N = geo.TEX
MPP = 2 * geo.EXTENT / N  # metres per pixel
OUT = os.path.join(os.path.dirname(__file__), "..", "build")


# ---------------------------------------------------------------- helpers
def px(pts):
    return [geo.to_px(x, y) for x, y in pts]


def grid():
    c = (np.arange(N, dtype=np.float32) + 0.5) * MPP - geo.EXTENT
    X = c[None, :].repeat(N, 0)
    Y = -c[:, None].repeat(N, 1)
    return X, Y


def draw(lines, width_m, size=N, circle=None):
    """Rasterise polylines (metres) into a float mask, supersampled 2x."""
    ss = 2
    im = Image.new("L", (size * ss, size * ss), 0)
    d = ImageDraw.Draw(im)
    w = max(1, int(round(width_m / MPP * ss)))
    for pts in lines:
        p = [(u * ss, v * ss) for u, v in px(pts)]
        d.line(p, fill=255, width=w, joint="curve")
        for u, v in p:  # round caps
            d.ellipse([u - w / 2, v - w / 2, u + w / 2, v + w / 2], fill=255)
    im = im.resize((size, size), Image.BILINEAR)
    return np.asarray(im, dtype=np.float32) / 255.0


def sample(img, x, y):
    u, v = geo.to_px(np.asarray(x), np.asarray(y))
    u = np.clip(u.astype(int), 0, N - 1)
    v = np.clip(v.astype(int), 0, N - 1)
    return img[v, u]


def year_at_pop(frac, y0, y1):
    """Invert the population curve between y0 and y1 (frac in 0..1)."""
    ys = np.arange(y0, y1 + 0.01, 0.05)
    yr, pp = zip(*geo.POPULATION)
    pop = np.interp(ys, yr, pp)
    pop = np.maximum.accumulate(pop)
    f = (pop - pop[0]) / (pop[-1] - pop[0])
    return np.interp(frac, f, ys)


def meander(pts, amp, wl):
    pts = np.asarray(pts, float)
    out = []
    acc = 0.0
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        L = np.hypot(x1 - x0, y1 - y0)
        nx, ny = -(y1 - y0) / L, (x1 - x0) / L
        for t in np.arange(0, L, 8.0):
            o = amp * (np.sin((acc + t) / wl * 2 * np.pi) + 0.5 * np.sin((acc + t) / wl * 5.3))
            out.append((x0 + (x1 - x0) * t / L + nx * o, y0 + (y1 - y0) * t / L + ny * o))
        acc += L
    out.append(tuple(pts[-1]))
    return out


_FIELDS = {}


def field(x, y, cells):
    """Smooth unit-variance noise sampled at world positions."""
    if cells not in _FIELDS:
        f = ndimage.gaussian_filter(np.random.default_rng(cells).normal(0, 1, (cells * 8, cells * 8)), 4)
        _FIELDS[cells] = (f - f.mean()) / f.std()
    f = _FIELDS[cells]
    n = f.shape[0]
    u = np.clip(((np.asarray(x) + geo.EXTENT) / (2 * geo.EXTENT) * n).astype(int), 0, n - 1)
    v = np.clip(((geo.EXTENT - np.asarray(y)) / (2 * geo.EXTENT) * n).astype(int), 0, n - 1)
    return f[v, u]


def circle_pts(c, r, n=96):
    a = np.linspace(0, 2 * np.pi, n + 1)
    return [(c[0] + r * np.cos(t), c[1] + r * np.sin(t)) for t in a]


# ---------------------------------------------------------------- terrain
def build_masks():
    X, Y = grid()
    river_line = draw([geo.RIVER], 4)
    d_river = ndimage.distance_transform_edt(river_line < 0.5) * MPP
    water = np.clip((geo.RIVER_HALF_WIDTH - d_river) / 6 + 0.5, 0, 1)
    bank = np.clip((geo.RIVER_HALF_WIDTH + geo.FLOODPLAIN - d_river) / 6 + 0.5, 0, 1)

    creek = draw([meander(geo.CREEK, 18.0, 160.0)], geo.CREEK_HALF_WIDTH * 2)
    barrier = (water > 0.5) | (creek > 0.5)
    lab, _ = ndimage.label(~barrier)

    def label_at(x, y):
        u, v = geo.to_px(x, y)
        return lab[int(v), int(u)]

    zone = np.zeros((N, N), np.uint8)
    zone[lab == label_at(0, 300)] = 1          # Yonghe
    zone[lab == label_at(-2600, -2600)] = 2    # Zhonghe
    zone[lab == label_at(0, 3200)] = 3         # Taipei side
    zone[(zone == 0) & ~barrier] = 2
    area = (zone == 1).sum() * MPP * MPP / 1e6
    print(f"Yonghe modelled area: {area:.2f} km2 (real 5.71)")
    return X, Y, water, bank, creek, zone, d_river


def park_fields(X, Y):
    """Distance to each park edge, nearest-park index, and rho."""
    ds = []
    for _, (cx, cy), r, *_ in geo.PARKS:
        ds.append(np.hypot(X - cx, Y - cy) - r)
    ds = np.stack(ds)
    near = ds.argmin(0)
    rho = ds.min(0)
    return ds, near, rho


def build_roads(X, Y, zone, ds, near, rho):
    roads = np.zeros((N, N), np.float32)
    ryear = np.full((N, N), 3000.0, np.float32)

    def add(mask, year):
        nonlocal roads
        m = mask > 0.35
        ryear[m] = np.minimum(ryear[m], year)
        roads = np.maximum(roads, mask)

    # Concentric ring lanes and radial spokes around each park cell (Yonghe).
    yh = zone == 1
    cx = np.array([p[1][0] for p in geo.PARKS])[near]
    cy = np.array([p[1][1] for p in geo.PARKS])[near]
    rr = np.array([p[2] for p in geo.PARKS], np.float32)[near]
    k = np.floor((rho - 18 + 42) / 85)
    ring_d = np.abs(rho - 18 - k * 85)
    hw = np.where(k == 0, 7.0, 4.0)
    ring = np.clip(hw - ring_d + 0.5, 0, 1) * (rho > -5) * (k <= 6)
    ang = np.arctan2(Y - cy, X - cx)
    nsp = 10
    a_d = np.abs(((ang * nsp / (2 * np.pi)) + 0.5) % 1.0 - 0.5) * (2 * np.pi / nsp)
    spoke = np.clip(4.0 - a_d * (rho + rr) + 0.5, 0, 1) * (rho > 10)
    lanes = np.maximum(ring, spoke) * yh
    lane_year = 1958 + np.clip(rho / 45.0, 0, 16)
    m = lanes > 0.35
    ryear[m] = np.minimum(ryear[m], lane_year[m])
    roads = np.maximum(roads, lanes)

    # Rectilinear grids for Zhonghe and the Taipei side.
    for z, rot, sp, yr in ((2, 0.55, 90, 1962), (3, 0.12, 80, 1925)):
        c, s = np.cos(rot), np.sin(rot)
        u = X * c + Y * s
        v = -X * s + Y * c
        gu = np.abs(((u / sp) + 0.5) % 1 - 0.5) * sp
        gv = np.abs(((v / (sp * 1.4)) + 0.5) % 1 - 0.5) * sp * 1.4
        g = np.clip(4.5 - np.minimum(gu, gv) + 0.5, 0, 1) * (zone == z)
        add(g, yr)

    # Arterials, clipped where they would cross a park.
    inpark = (ds.min(0) < 10)
    for name, pts, hw_a, yr in geo.ARTERIALS:
        a = draw([pts], hw_a * 2) * ~inpark
        add(a, yr)
    roads *= (zone > 0)

    # Old country paths (dirt) that predate the plan.
    paths = []
    for _ in range(40):
        x, y = RNG.uniform(-2500, 2500), RNG.uniform(-2500, 2500)
        h = RNG.uniform(0, 2 * np.pi)
        pts = [(x, y)]
        for _ in range(25):
            h += RNG.normal(0, 0.25)
            x, y = x + 60 * np.cos(h), y + 60 * np.sin(h)
            pts.append((x, y))
        paths.append(pts)
    paths.append(geo.ARTERIALS[0][1])  # the road to the ferry/bridge
    dirt = draw(paths, 4) * (zone > 0)
    return roads, ryear, dirt


def build_plan(X, Y, zone):
    """1955 blueprint lines and the ghost outlines of the seven parks."""
    lines = []
    for _, c, r, *_ in geo.PARKS:
        lines += [circle_pts(c, r), circle_pts(c, r + 18), circle_pts(c, r + 103)]
    lines += [pts for _, pts, *_ in geo.ARTERIALS]
    plan = draw(lines, 5)
    # boundary of the planning area
    edge = ndimage.binary_dilation(zone == 1, iterations=3) & ~(zone == 1)
    plan = np.maximum(plan, ndimage.gaussian_filter(edge.astype(np.float32), 1.0) * 1.5)
    plan = np.clip(plan, 0, 1)
    order = np.clip(np.hypot(X - 0, Y - 300) / 2600.0, 0, 1)
    ghost = draw([circle_pts(c, r) for _, c, r, *_ in geo.PARKS], 7)
    fill = np.zeros_like(plan)
    for _, (cx, cy), r, *_ in geo.PARKS:
        fill = np.maximum(fill, (np.hypot(X - cx, Y - cy) < r).astype(np.float32))
    return plan, order, ghost, fill


# ---------------------------------------------------------------- sites
def build_sites(zone, roads, water, bank, X, Y):
    print("sites: distance field")
    rmask = roads > 0.35
    d_road, inds = ndimage.distance_transform_edt(~rmask, return_indices=True)
    d_road *= MPP

    sp = 17.0
    g = np.arange(-geo.EXTENT + 40, geo.EXTENT - 40, sp)
    sx, sy = np.meshgrid(g, g)
    sx = (sx + RNG.uniform(-2.5, 2.5, sx.shape)).ravel()
    sy = (sy + RNG.uniform(-2.5, 2.5, sy.shape)).ravel()
    u, v = geo.to_px(sx, sy)
    u = np.clip(u.astype(int), 0, N - 1)
    v = np.clip(v.astype(int), 0, N - 1)
    z = zone[v, u]
    dr = d_road[v, u]
    keep = (z > 0) & (dr > 7.5) & (bank[v, u] < 0.1)
    # thin out the far distance (never seen up close)
    far = np.hypot(sx, sy - 200) > 2800
    keep &= ~(far & (RNG.random(sx.shape) < 0.35))
    sx, sy, u, v, z, dr = sx[keep], sy[keep], u[keep], v[keep], z[keep], dr[keep]

    # face the nearest road
    ny_, nx_ = inds[0][v, u], inds[1][v, u]
    rx = (nx_ + 0.5) * MPP - geo.EXTENT
    ry = geo.EXTENT - (ny_ + 0.5) * MPP
    rot = np.arctan2(ry - sy, rx - sx)
    n = len(sx)
    print("candidate sites:", n)

    # parks: which sites sit inside a park, and when that land is released
    released = np.zeros(n)          # year the park land becomes buildable
    park_of = np.zeros(n, int)
    for pid, (cx, cy), r, fate, conv, keep_f in geo.PARKS:
        inside = np.hypot(sx - cx, sy - cy) < r + 12
        park_of[inside] = pid
        if fate == "zhonghe":
            released[inside] = 9999
        elif fate == "renai":
            # western part survives as 仁愛公園
            survive = inside & ((sx - cx) < -r + 2 * r * keep_f)
            released[survive] = 9999
            released[inside & ~survive] = conv
        elif fate in ("school", "gov"):
            released[inside] = 9999  # compounds are placed separately
        else:
            released[inside] = conv

    # Dachen New Village footprint keeps its own row houses
    dcx, dcy = geo.DACHEN_CENTER
    ca, sa = np.cos(geo.DACHEN_ANGLE), np.sin(geo.DACHEN_ANGLE)
    lx = (sx - dcx) * ca + (sy - dcy) * sa
    ly = -(sx - dcx) * sa + (sy - dcy) * ca
    in_dachen = (np.abs(lx) < geo.DACHEN_SIZE[0] / 2 + 8) & (np.abs(ly) < geo.DACHEN_SIZE[1] / 2 + 8)

    # Development order: outward from the bridge, faster along arterials.
    bx, by = geo.BRIDGE_A
    dist_b = np.hypot(sx - bx, sy - by)
    noise = ndimage.gaussian_filter(RNG.normal(0, 1, (64, 64)), 3)
    noise = (noise - noise.mean()) / noise.std()
    nz = noise[np.clip(((sy + geo.EXTENT) / (2 * geo.EXTENT) * 64).astype(int), 0, 63),
               np.clip(((sx + geo.EXTENT) / (2 * geo.EXTENT) * 64).astype(int), 0, 63)]
    art = draw([pts for _, pts, *_ in geo.ARTERIALS], 120)
    near_art = sample(art, sx, sy)
    key = dist_b + 450 * nz - 500 * near_art + RNG.normal(0, 180, n)

    birth_p = np.full(n, 9999.0)   # single-storey house (平房)
    birth_a = np.full(n, 9999.0)   # walk-up apartment (公寓)
    birth_t = np.full(n, 9999.0)   # later tower
    a_type = np.zeros(n, int)      # 0 apt 3-7F, 1 mid 7-12F

    for zid, p0, (a0, a1), lag in ((1, (1946, 1966), (1961, 1991), 0),
                                         (2, (1950, 1972), (1966, 1996), 0),
                                         (3, (1900, 1938), (1950, 1985), 0)):
        m = (z == zid) & ~in_dachen & (released < 9999)
        idx = np.where(m)[0]
        order = np.argsort(np.argsort(key[idx])) / max(1, len(idx) - 1)
        # 平房 for the first 55%
        pm = order < (0.9 if zid == 3 else 0.55)
        pfrac = order / (0.9 if zid == 3 else 0.55)
        if zid == 1:
            birth_p[idx[pm]] = year_at_pop(pfrac[pm], *p0)
        else:
            birth_p[idx[pm]] = p0[0] + (p0[1] - p0[0]) * pfrac[pm] ** 1.2
        q = np.clip(order + RNG.normal(0, 0.12, len(idx)), 0, 1)
        if zid == 1:
            ya = year_at_pop(q, *[a0, a1])
        else:
            ya = a0 + (a1 - a0) * q ** 1.1
        birth_a[idx] = np.maximum(ya, np.where(pm, birth_p[idx] + 7, 0))
        # parks converted to housing
        birth_a[idx] = np.maximum(birth_a[idx], released[idx] + RNG.uniform(0, 4, len(idx)))
        late = birth_a[idx] > 1979
        a_type[idx] = np.where(late & (RNG.random(len(idx)) < 0.45), 1, 0)
        a_type[idx] = np.where(RNG.random(len(idx)) < 0.06, 1, a_type[idx])
        # towers after 1995 near the MRT and the bridgehead, or on the Taipei side
        if zid == 3:
            tp = RNG.random(len(idx)) < 0.10
            birth_t[idx[tp]] = RNG.uniform(1985, 2020, tp.sum())
        else:
            hub = np.minimum(np.hypot(sx[idx] + 380, sy[idx] - 1050),
                             np.hypot(sx[idx] + 650, sy[idx] + 40))
            pt = 0.025 + 0.12 * np.exp(-hub / 350)
            tp = RNG.random(len(idx)) < pt
            birth_t[idx[tp]] = RNG.uniform(1997, 2022, tp.sum())

    # ---- assemble categories
    cats = {}

    def pack(xx, yy, birth, death, w, d, h, rr, tint=None):
        k = len(xx)
        if tint is None:
            tint = RNG.random(k)
        return dict(x=np.asarray(xx, np.float32), y=np.asarray(yy, np.float32),
                    birth=np.asarray(birth, np.float32), death=np.asarray(death, np.float32),
                    w=np.asarray(w, np.float32), d=np.asarray(d, np.float32),
                    h=np.asarray(h, np.float32), rot=np.asarray(rr, np.float32),
                    tint=np.asarray(tint, np.float32))

    def m_(sel):
        return sx[sel], sy[sel], rot[sel]

    # 平房 single-storey houses
    sel = birth_p < 9000
    xx, yy, rr = m_(sel)
    k = sel.sum()
    cats["pinfang"] = pack(xx, yy, birth_p[sel], birth_a[sel], RNG.uniform(11, 15, k),
                           RNG.uniform(13, 16.5, k), RNG.uniform(3.6, 4.4, k), rr)
    # 公寓 apartments (3–7 floors)
    sel = (birth_a < 9000) & (a_type == 0)
    xx, yy, rr = m_(sel)
    k = sel.sum()
    fl_field = field(xx, yy, 9)
    floors = np.clip(np.round(4.3 + 1.1 * fl_field + RNG.normal(0, 0.45, k)), 3, 7)
    cats["apt"] = pack(xx, yy, birth_a[sel], birth_t[sel], RNG.uniform(15.5, 19, k),
                       RNG.uniform(16.5, 18.5, k), floors * 3.2 + 0.6, rr)
    # 大樓 mid-rise (7–12 floors)
    sel = (birth_a < 9000) & (a_type == 1)
    xx, yy, rr = m_(sel)
    k = sel.sum()
    floors = RNG.integers(7, 13, k)
    cats["mid"] = pack(xx, yy, birth_a[sel], birth_t[sel], RNG.uniform(16, 21, k),
                       RNG.uniform(16.5, 20, k), floors * 3.2 + 1.0, rr)
    # towers (14–28 floors)
    sel = birth_t < 9000
    xx, yy, rr = m_(sel)
    k = sel.sum()
    floors = RNG.integers(14, 29, k)
    cats["tower"] = pack(xx, yy, birth_t[sel], np.full(k, 9999), RNG.uniform(19, 26, k),
                         RNG.uniform(18, 24, k), floors * 3.2 + 2.0, rr)

    # farmhouses (合院): scattered, die when their neighbourhood urbanises
    first = np.minimum(birth_p, birth_a)
    tree = cKDTree(np.c_[sx, sy])
    cand = np.where(((z == 1) | (z == 2)) & (first < 9000))[0]
    pick = RNG.choice(cand, 110, replace=False)
    fb, fd = [], []
    for i in pick:
        nb = tree.query_ball_point([sx[i], sy[i]], 30)
        fd.append(min(first[nb].min(), 1975))
        fb.append(RNG.uniform(1730, 1900))
        first[nb] = np.maximum(first[nb], 0)
    k = len(pick)
    cats["farm"] = pack(sx[pick], sy[pick], fb, fd, np.full(k, 1.0), np.full(k, 1.0),
                        np.full(k, 1.0), rot[pick] + RNG.choice([0, np.pi / 2], k))
    # neighbours of a living farmhouse are fields until it goes
    # (handled by the farmhouse dying at the first neighbour's birth)

    # indigenous huts (秀朗社 near the south-east river bend, 龜崙蘭社 inland)
    hx, hy = [], []
    for (cx, cy), nh in (((1500, -1300), 14), ((-300, 500), 12)):
        a = RNG.uniform(0, 2 * np.pi, nh)
        r = RNG.uniform(10, 70, nh)
        hx += list(cx + r * np.cos(a))
        hy += list(cy + r * np.sin(a))
    k = len(hx)
    cats["hut"] = pack(hx, hy, np.full(k, 1500), np.full(k, 1760), RNG.uniform(5, 7, k),
                       RNG.uniform(5, 7, k), RNG.uniform(3.5, 4.5, k), RNG.uniform(0, 6.28, k))

    # Dachen row houses: rows parallel to the river, 1955–56
    rows = []
    W, D = geo.DACHEN_SIZE
    for j, ly0 in enumerate(np.arange(-D / 2 + 8, D / 2 - 4, 13.0)):
        for lx0 in np.arange(-W / 2 + 10, W / 2 - 10, 24.0):
            gx = dcx + lx0 * ca - ly0 * sa
            gy = dcy + lx0 * sa + ly0 * ca
            rows.append((gx, gy))
    rows = np.array(rows)
    k = len(rows)
    cats["dachen"] = pack(rows[:, 0], rows[:, 1], RNG.uniform(1955.2, 1956.3, k),
                          np.full(k, 9999), np.full(k, 22.0), np.full(k, 7.5),
                          RNG.uniform(3.2, 3.6, k), np.full(k, geo.DACHEN_ANGLE + np.pi / 2))
    # later additions (加蓋) on Dachen rows
    k2 = k // 3
    pk = RNG.choice(k, k2, replace=False)
    cats["dachen_add"] = pack(rows[pk, 0] + RNG.normal(0, 2, k2), rows[pk, 1] + RNG.normal(0, 2, k2),
                              RNG.uniform(1975, 2000, k2), np.full(k2, 9999), RNG.uniform(5, 8, k2),
                              RNG.uniform(5, 7, k2), RNG.uniform(6.5, 7.2, k2),
                              np.full(k2, geo.DACHEN_ANGLE + np.pi / 2))

    # School / government compounds in parks 2, 3, 5 and the east of park 1
    comp = {"x": [], "y": [], "b": [], "w": [], "d": [], "h": [], "r": []}
    for pid, (cx, cy), r, fate, conv, keep_f in geo.PARKS:
        if fate in ("school", "gov") or fate == "renai":
            ox = cx + (r * 0.5 if fate == "renai" else 0)
            bars = [(0, r * 0.55, r * 1.1, 14, 0), (-r * 0.55, 0, 14, r * 0.9, 0),
                    (r * 0.55, 0, 14, r * 0.9, 0)]
            if fate == "gov":
                bars = [(0, 0, 60, 40, 0), (-r * 0.5, -r * 0.3, 30, 50, 0), (r * 0.45, r * 0.2, 40, 30, 0),
                        (0, -r * 0.6, 70, 20, 0)]
            if fate == "renai":
                bars = [(r * 0.25, r * 0.3, 14, r * 0.6, 0), (r * 0.25, -r * 0.35, 14, r * 0.5, 0)]
            for bx_, by_, w_, d_, _ in bars:
                comp["x"].append(ox + bx_)
                comp["y"].append(cy + by_)
                comp["b"].append(conv + RNG.uniform(0, 2))
                comp["w"].append(w_)
                comp["d"].append(d_)
                comp["h"].append(4 * 3.6 + 1)
                comp["r"].append(0.0)
    k = len(comp["x"])
    cats["compound"] = pack(comp["x"], comp["y"], comp["b"], np.full(k, 9999), comp["w"],
                            comp["d"], comp["h"], comp["r"])

    # Trees: parks (die at conversion), field edges (die with urbanisation),
    # and street trees along arterials after 1975.
    tx, ty, tb, td, ts = [], [], [], [], []
    for pid, (cx, cy), r, fate, conv, keep_f in geo.PARKS:
        nt = int(r * r / 260)
        a = RNG.uniform(0, 2 * np.pi, nt)
        rr_ = r * np.sqrt(RNG.uniform(0.0, 1, nt)) * 0.95
        xx = cx + rr_ * np.cos(a)
        yy = cy + rr_ * np.sin(a)
        if fate == "zhonghe":
            death = np.full(nt, 9999)
        elif fate == "renai":
            death = np.where((xx - cx) < -r + 2 * r * keep_f, 9999, conv)
        else:
            death = np.full(nt, conv)
        tx += list(xx); ty += list(yy); tb += list(RNG.uniform(1956, 1962, nt)); td += list(death)
        ts += list(RNG.uniform(0.8, 1.3, nt))
    # field trees / bamboo clumps near farmhouses
    f = cats["farm"]
    for x0, y0, b0, d0 in zip(f["x"], f["y"], f["birth"], f["death"]):
        nt = RNG.integers(4, 10)
        a = RNG.uniform(0, 2 * np.pi, nt)
        rr_ = RNG.uniform(18, 35, nt)
        tx += list(x0 + rr_ * np.cos(a)); ty += list(y0 + rr_ * np.sin(a))
        tb += [b0] * nt; td += [d0] * nt; ts += list(RNG.uniform(0.9, 1.5, nt))
    # wild woodland before farming
    nt = 40000
    wx = RNG.uniform(-3300, 3300, nt)
    wy = RNG.uniform(-3300, 3300, nt)
    ok = field(wx, wy, 14) > 0.35
    ok &= sample(zone, wx, wy) > 0
    ok &= sample(water, wx, wy) < 0.1
    wx, wy = wx[ok], wy[ok]
    nt = len(wx)
    tx += list(wx); ty += list(wy); tb += [1500] * nt
    td += list(RNG.uniform(1720, 1820, nt)); ts += list(RNG.uniform(1.0, 1.8, nt))
    # street trees
    for name, pts, hw_a, yr in geo.ARTERIALS:
        pts = np.array(pts, float)
        for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
            L = np.hypot(x1 - x0, y1 - y0)
            nx_, ny2 = -(y1 - y0) / L, (x1 - x0) / L
            for t in np.arange(0, L, 14):
                for s in (-1, 1):
                    xx = x0 + (x1 - x0) * t / L + s * nx_ * (hw_a + 1.5)
                    yy = y0 + (y1 - y0) * t / L + s * ny2 * (hw_a + 1.5)
                    tx.append(xx); ty.append(yy); tb.append(RNG.uniform(1975, 1990))
                    td.append(9999); ts.append(RNG.uniform(0.45, 0.6))
    tx, ty = np.array(tx), np.array(ty)
    k = len(tx)
    cats["tree"] = pack(tx, ty, tb, td, ts, ts, ts, RNG.uniform(0, 6.28, k))

    # ground urbanisation year: first building on/near each pixel
    G = 1024
    gyear = np.full((G, G), 9999.0, np.float32)
    first = np.minimum(np.minimum(birth_p, birth_a), birth_t)
    gu = np.clip(((sx + geo.EXTENT) / (2 * geo.EXTENT) * G).astype(int), 0, G - 1)
    gv = np.clip(((geo.EXTENT - sy) / (2 * geo.EXTENT) * G).astype(int), 0, G - 1)
    np.minimum.at(gyear, (gv, gu), first.astype(np.float32))
    for nm in ("dachen", "compound"):
        c = cats[nm]
        gu = np.clip(((c["x"] + geo.EXTENT) / (2 * geo.EXTENT) * G).astype(int), 0, G - 1)
        gv = np.clip(((geo.EXTENT - c["y"]) / (2 * geo.EXTENT) * G).astype(int), 0, G - 1)
        np.minimum.at(gyear, (gv, gu), c["birth"] - 0.5)
    gyear = ndimage.grey_erosion(gyear, size=(4, 4))
    gyear = np.minimum(gyear, ndimage.grey_erosion(gyear, size=(13, 13)) + 2.0)
    for k_, v_ in cats.items():
        print(f"  {k_:11s} {len(v_['x']):6d}")
    return cats, gyear


def main():
    os.makedirs(OUT, exist_ok=True)
    X, Y, water, bank, creek, zone, d_river = build_masks()
    ds, near, rho = park_fields(X, Y)
    roads, ryear, dirt = build_roads(X, Y, zone, ds, near, rho)
    plan, order, ghost, pfill = build_plan(X, Y, zone)
    cats, gyear = build_sites(zone, roads, water, bank, X, Y)

    # park id map (only inside park circles)
    pid = np.zeros((N, N), np.float32)
    for i, (_, (cx, cy), r, *_) in enumerate(geo.PARKS):
        pid[(np.hypot(X - cx, Y - cy) < r)] = i + 1
    # school running tracks in parks 2 and 5
    track = np.zeros((N, N), np.float32)
    for i in (1, 4):
        _, (cx, cy), r, *_ = geo.PARKS[i]
        ex = ((X - cx) / (r * 0.55)) ** 2 + ((Y - cy + r * 0.15) / (r * 0.33)) ** 2
        track = np.maximum(track, ((ex < 1) & (ex > 0.62)).astype(np.float32))
        track = np.maximum(track, 0.5 * (ex <= 0.62))
    ryear_n = np.clip((ryear - 1600) / 500.0, 0, 1)
    np.savez_compressed(
        os.path.join(OUT, "layout.npz"),
        roads=roads.astype(np.float16), ryear=ryear_n.astype(np.float16), dirt=dirt.astype(np.float16),
        water=water.astype(np.float16), bank=bank.astype(np.float16), creek=creek.astype(np.float16),
        zone=zone, pid=pid.astype(np.float16), track=track.astype(np.float16),
        plan=plan.astype(np.float16), order=order.astype(np.float16), ghost=ghost.astype(np.float16),
        pfill=pfill.astype(np.float16),
        gyear=np.clip((gyear - 1600) / 500.0, 0, 1).astype(np.float16),
        d_river=np.minimum(d_river, 2000).astype(np.float16),
        **{f"{c}__{k}": v for c, d in cats.items() for k, v in d.items()},
    )
    # preview
    prev = np.zeros((N, N, 3), np.float32)
    prev[zone == 1] = (0.55, 0.6, 0.45)
    prev[zone == 2] = (0.45, 0.5, 0.4)
    prev[zone == 3] = (0.4, 0.45, 0.42)
    prev[water > 0.5] = (0.2, 0.3, 0.45)
    prev[pid > 0] = (0.2, 0.55, 0.25)
    prev = prev * (1 - roads[..., None] * 0.7)
    prev[plan > 0.5] = (0.3, 0.7, 1.0)
    Image.fromarray((prev * 255).astype(np.uint8)).resize((1024, 1024)).save(os.path.join(OUT, "layout_preview.png"))


if __name__ == "__main__":
    main()
