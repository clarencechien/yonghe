"""Keyframe curves shared by the renderer and the compositor (no bpy)."""


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
