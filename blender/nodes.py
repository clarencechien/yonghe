"""Tiny helper for building Blender node trees from Python."""
import bpy


class NT:
    def __init__(self, tree):
        self.t = tree
        self.nodes = tree.nodes
        self.links = tree.links

    def node(self, typ, inputs=None, **props):
        nd = self.nodes.new(typ)
        for k, v in props.items():
            setattr(nd, k, v)
        for k, v in (inputs or {}).items():
            self.set(nd.inputs[k], v)
        return nd

    def set(self, sock, v):
        if isinstance(v, bpy.types.NodeSocket):
            self.links.new(v, sock)
        elif isinstance(v, bpy.types.Node):
            self.links.new(v.outputs[0], sock)
        else:
            sock.default_value = v

    # -- scalar math
    def math(self, op, a, b=0.0, c=0.0, clamp=False):
        nd = self.node("ShaderNodeMath", operation=op, use_clamp=clamp)
        self.set(nd.inputs[0], a)
        if len(nd.inputs) > 1:
            self.set(nd.inputs[1], b)
        if len(nd.inputs) > 2:
            self.set(nd.inputs[2], c)
        return nd.outputs[0]

    def add(self, a, b):
        return self.math("ADD", a, b)

    def sub(self, a, b):
        return self.math("SUBTRACT", a, b)

    def mul(self, a, b, clamp=False):
        return self.math("MULTIPLY", a, b, clamp=clamp)

    def gt(self, a, b):
        return self.math("GREATER_THAN", a, b)

    def lt(self, a, b):
        return self.math("LESS_THAN", a, b)

    def maxi(self, a, b):
        return self.math("MAXIMUM", a, b)

    def mini(self, a, b):
        return self.math("MINIMUM", a, b)

    def inv(self, a):
        return self.math("SUBTRACT", 1.0, a, clamp=True)

    def smooth(self, x, lo, hi):
        nd = self.node("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP", clamp=True)
        self.set(nd.inputs["Value"], x)
        self.set(nd.inputs["From Min"], lo)
        self.set(nd.inputs["From Max"], hi)
        return nd.outputs["Result"]

    def maprange(self, x, a, b, c, d):
        nd = self.node("ShaderNodeMapRange", clamp=True)
        for k, v in zip(("Value", "From Min", "From Max", "To Min", "To Max"), (x, a, b, c, d)):
            self.set(nd.inputs[k], v)
        return nd.outputs["Result"]

    # -- vectors / colours
    def sep(self, v):
        nd = self.node("ShaderNodeSeparateXYZ")
        self.set(nd.inputs[0], v)
        return nd.outputs

    def comb(self, x, y, z):
        nd = self.node("ShaderNodeCombineXYZ")
        for i, v in enumerate((x, y, z)):
            self.set(nd.inputs[i], v)
        return nd.outputs[0]

    def vmath(self, op, a, b=(0, 0, 0)):
        nd = self.node("ShaderNodeVectorMath", operation=op)
        self.set(nd.inputs[0], a)
        self.set(nd.inputs[1], b)
        return nd.outputs[0] if op not in ("LENGTH", "DOT_PRODUCT", "DISTANCE") else nd.outputs[1]

    def mixc(self, fac, a, b):
        nd = self.node("ShaderNodeMix", data_type="RGBA", clamp_factor=True)
        self.set(nd.inputs[0], fac)
        self.set(nd.inputs[6], a)
        self.set(nd.inputs[7], b)
        return nd.outputs[2]

    def rgb(self, c):
        nd = self.node("ShaderNodeRGB")
        nd.outputs[0].default_value = (*c, 1.0) if len(c) == 3 else c
        return nd.outputs[0]

    def ramp(self, fac, stops, interp="LINEAR"):
        nd = self.node("ShaderNodeValToRGB")
        cr = nd.color_ramp
        cr.interpolation = interp
        while len(cr.elements) < len(stops):
            cr.elements.new(0.5)
        for el, (pos, col) in zip(cr.elements, stops):
            el.position = pos
            el.color = (*col, 1.0) if len(col) == 3 else col
        self.set(nd.inputs[0], fac)
        return nd.outputs[0]

    def noise(self, vec, scale, detail=2.0, rough=0.5):
        nd = self.node("ShaderNodeTexNoise", inputs={"Scale": scale, "Detail": detail, "Roughness": rough})
        self.set(nd.inputs["Vector"], vec)
        return nd.outputs["Fac"]

    def white(self, vec, dims="3D"):
        nd = self.node("ShaderNodeTexWhiteNoise", noise_dimensions=dims)
        self.set(nd.inputs["Vector"], vec)
        return nd.outputs["Value"]


def drive(socket_owner, path, scene, prop, index=-1):
    """Drive `socket_owner.path` from scene[prop] without Python expressions."""
    fc = socket_owner.driver_add(path, index) if index >= 0 else socket_owner.driver_add(path)
    drv = fc.driver
    drv.type = "AVERAGE"
    var = drv.variables.new()
    var.type = "SINGLE_PROP"
    var.targets[0].id_type = "SCENE"
    var.targets[0].id = scene
    var.targets[0].data_path = f'["{prop}"]'
    return fc


def driven_value(nt, scene, prop):
    """A Value node whose output follows scene[prop]."""
    nd = nt.node("ShaderNodeValue")
    drive(nd.outputs[0], "default_value", scene, prop)
    return nd.outputs[0]
