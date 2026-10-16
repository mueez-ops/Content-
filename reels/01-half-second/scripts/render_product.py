"""Builds the stand-in product (a perfume bottle) in Blender and renders every 3D shot.

Usage (bpy as a Python module):
    python render_product.py <shot> [--res 1080x1920] [--samples 48] [--frames a-b]

Each shot writes a PNG sequence to renders/<shot>/####.png.
Swap these renders for real phone footage of your own product at any time;
compose.py only expects one PNG sequence (or folder of frames) per shot.
"""
import math
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "renders")


# ---------------------------------------------------------------- helpers
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def mat_principled(name, color=(1, 1, 1), metallic=0.0, rough=0.5, transmission=0.0,
                   ior=1.45, emission=None, emission_strength=0.0, coat=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Roughness"].default_value = rough
    b.inputs["Transmission Weight"].default_value = transmission
    b.inputs["IOR"].default_value = ior
    b.inputs["Coat Weight"].default_value = coat
    if emission:
        b.inputs["Emission Color"].default_value = (*emission, 1)
        b.inputs["Emission Strength"].default_value = emission_strength
    return m


def mat_liquid(name, color, density):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (1, 1, 1, 1)
    b.inputs["Transmission Weight"].default_value = 1.0
    b.inputs["Roughness"].default_value = 0.0
    b.inputs["IOR"].default_value = 1.33
    vol = nt.nodes.new("ShaderNodeVolumeAbsorption")
    vol.inputs["Color"].default_value = (*color, 1)
    vol.inputs["Density"].default_value = density
    out = nt.nodes["Material Output"]
    nt.links.new(vol.outputs["Volume"], out.inputs["Volume"])
    return m


def mat_emit(name, strength=10.0, color=(1, 1, 1)):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (*color, 1)
    e.inputs["Strength"].default_value = strength
    lp = nt.nodes.new("ShaderNodeLightPath")
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    # Visible in reflections/refractions only, invisible to the camera.
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
    nt.links.new(e.outputs[0], mix.inputs[1])
    nt.links.new(tr.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], o.inputs["Surface"])
    return m


def add_box(name, size, loc, bevel=0.06, segs=6, mat=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = size
    bpy.ops.object.transform_apply(scale=True)
    if bevel:
        mod = o.modifiers.new("bevel", "BEVEL")
        mod.width = bevel
        mod.segments = segs
        mod.limit_method = "NONE"
    bpy.ops.object.shade_smooth()
    if mat:
        o.data.materials.append(mat)
    return o


def add_cyl(name, r, depth, loc, mat=None, verts=96, bevel=0.0):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=depth, location=loc, vertices=verts)
    o = bpy.context.object
    o.name = name
    if bevel:
        mod = o.modifiers.new("bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 4
        mod.limit_method = "ANGLE"
    bpy.ops.object.shade_smooth()
    if mat:
        o.data.materials.append(mat)
    return o


def add_text(body, size, loc, mat, font=None, extrude=0.002, spacing=1.0, rot=(math.radians(90), 0, 0)):
    bpy.ops.object.text_add(location=loc, rotation=rot)
    t = bpy.context.object
    t.data.body = body
    t.data.size = size
    t.data.align_x = "CENTER"
    t.data.align_y = "CENTER"
    t.data.extrude = extrude
    t.data.space_character = spacing
    if font:
        t.data.font = bpy.data.fonts.load(font)
    t.data.materials.append(mat)
    return t


def look_at(obj, target):
    d = Vector(target) - obj.location
    obj.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def area(name, loc, target, size, energy, color=(1, 1, 1), shape="RECTANGLE", size_y=None):
    bpy.ops.object.light_add(type="AREA", location=loc)
    l = bpy.context.object
    l.name = name
    l.data.shape = shape
    l.data.size = size
    if size_y is not None:
        l.data.size_y = size_y
    l.data.energy = energy
    l.data.color = color
    look_at(l, target)
    return l


def strip(name, loc, target, w, h, strength):
    """Long emissive card: gives glass its crisp vertical highlights."""
    bpy.ops.mesh.primitive_plane_add(size=1, location=loc)
    p = bpy.context.object
    p.name = name
    p.scale = (w, h, 1)
    look_at(p, target)
    p.rotation_euler.rotate_axis("X", math.radians(180))
    p.data.materials.append(mat_emit(name + "_m", strength))
    return p


# ---------------------------------------------------------------- product
FONT_SERIF = os.path.join(ROOT, "assets", "fonts", "InstrumentSerif-Regular.ttf")
FONT_MONO = os.path.join(ROOT, "assets", "fonts", "SpaceMono-Regular.ttf")


def build_bottle():
    """Heavy rectangular perfume flacon: thick glass, amber juice, gold collar, black cap."""
    root = bpy.data.objects.new("BOTTLE", None)
    bpy.context.collection.objects.link(root)

    glass = mat_principled("glass", (1, 1, 1), rough=0.0, transmission=1.0, ior=1.5)
    juice = mat_liquid("juice", (1.0, 0.55, 0.18), 3.2)
    gold = mat_principled("gold", (1.0, 0.72, 0.38), metallic=1.0, rough=0.18)
    cap = mat_principled("cap", (0.015, 0.015, 0.017), rough=0.12, coat=1.0)
    label = mat_principled("label", (0.96, 0.92, 0.84), rough=0.35)

    W, H, D = 1.0, 1.2, 0.56
    parts = []
    parts.append(add_box("glass", (W, D, H), (0, 0, H / 2), bevel=0.07, segs=8, mat=glass))
    # Juice sits inside the thick walls (base is extra thick, like a real flacon).
    parts.append(add_box("juice", (W - 0.16, D - 0.14, H - 0.36), (0, 0, 0.24 + (H - 0.36) / 2 - 0.02),
                         bevel=0.03, segs=4, mat=juice))
    parts.append(add_cyl("collar", 0.17, 0.12, (0, 0, H + 0.06), mat=gold, bevel=0.01))
    parts.append(add_box("cap", (0.52, 0.52, 0.5), (0, 0, H + 0.12 + 0.25), bevel=0.04, segs=6, mat=cap))
    parts.append(add_box("capband", (0.535, 0.535, 0.035), (0, 0, H + 0.12 + 0.05), bevel=0.01, segs=2, mat=gold))
    # Front label.
    lab = add_box("label", (0.62, 0.006, 0.36), (0, -D / 2 - 0.004, H * 0.5), bevel=0.004, segs=2, mat=label)
    parts.append(lab)
    t1 = add_text("VELOUR", 0.13, (0, -D / 2 - 0.0085, H * 0.5 + 0.035), mat_principled("ink", (0.02, 0.02, 0.02), rough=0.4),
                  font=FONT_SERIF, extrude=0.0005, spacing=1.15)
    t2 = add_text("EAU DE PARFUM  ·  N°05", 0.034, (0, -D / 2 - 0.0085, H * 0.5 - 0.085), gold,
                  font=FONT_MONO, extrude=0.0004, spacing=1.2)
    parts += [t1, t2]
    for p in parts:
        p.parent = root
    return root


def sweep(color=(0.02, 0.02, 0.022), rough=0.25, size=40, floor=None):
    """Seamless floor + backdrop."""
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, 0))
    f = bpy.context.object
    f.data.materials.append(mat_principled("floor", floor or color, rough=rough))
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 12, size / 2), rotation=(math.radians(90), 0, 0))
    b = bpy.context.object
    b.data.materials.append(mat_principled("back", color, rough=0.8))
    return f, b


def world(color=(0, 0, 0), strength=0.0):
    w = bpy.data.worlds.new("w")
    bpy.context.scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (*color, 1)
    bg.inputs["Strength"].default_value = strength


def camera(loc, target, lens=50, dof=None, fstop=2.8):
    bpy.ops.object.camera_add(location=loc)
    c = bpy.context.object
    c.data.lens = lens
    look_at(c, target)
    if dof:
        c.data.dof.use_dof = True
        c.data.dof.focus_distance = dof
        c.data.dof.aperture_fstop = fstop
    bpy.context.scene.camera = c
    return c


def key(obj, frame, **props):
    for k, v in props.items():
        setattr(obj, k, v)
        obj.keyframe_insert(k, frame=frame)


def ease_all(kind="BEZIER"):
    for a in bpy.data.actions:
        for fc in getattr(a, "fcurves", []):
            for kp in fc.keyframe_points:
                kp.interpolation = kind


def studio_dark():
    world((0, 0, 0), 0)
    sweep()
    area("key", (-2.6, -2.4, 2.6), (0, 0, 0.7), 1.6, 260, (1.0, 0.86, 0.72))
    area("rimL", (-2.0, 1.6, 1.4), (0, 0, 0.8), 0.6, 220, (1.0, 0.75, 0.5), size_y=3.0)
    area("rimR", (2.0, 1.6, 1.4), (0, 0, 0.8), 0.6, 160, (0.85, 0.9, 1.0), size_y=3.0)
    area("top", (0, 0, 4.0), (0, 0, 0), 1.2, 60)
    strip("stripL", (-1.6, -1.4, 0.9), (0, 0, 0.8), 0.25, 3.0, 14)
    strip("stripR", (1.7, -1.0, 0.9), (0, 0, 0.8), 0.18, 3.0, 9)


# ---------------------------------------------------------------- shots
def shot_boring(scn):
    """Flat, front-on, over-lit catalogue shot: the 'boring ad'."""
    world((0.85, 0.85, 0.85), 1.15)
    sweep((0.78, 0.78, 0.78), rough=0.9)
    build_bottle()
    area("flat", (0, -5, 1.0), (0, 0, 0.8), 6, 900)
    camera((0, -6.2, 0.85), (0, 0, 0.85), lens=60)
    scn.frame_start = scn.frame_end = 1


def shot_glass_macro(scn):
    """Low macro slide across the thick glass base while a light strip blooms through."""
    studio_dark()
    build_bottle()
    c = camera((-0.75, -1.35, 0.2), (-0.32, -0.28, 0.3), lens=60, dof=1.15, fstop=2.4)
    key(c, 1, location=(-0.85, -1.30, 0.16))
    key(c, 15, location=(-0.62, -1.40, 0.26))
    s = bpy.data.objects["stripL"]
    key(s, 1, location=(-2.4, -1.2, 0.9))
    key(s, 15, location=(-0.6, -1.9, 0.9))
    ease_all("LINEAR")
    scn.frame_start, scn.frame_end = 1, 15


def shot_cap_macro(scn):
    studio_dark()
    b = build_bottle()
    camera((0.55, -1.25, 1.62), (0, 0, 1.45), lens=90, dof=1.37, fstop=2.0)
    key(b, 1, rotation_euler=(0, 0, math.radians(-16)))
    key(b, 20, rotation_euler=(0, 0, math.radians(14)))
    ease_all("LINEAR")
    scn.frame_start, scn.frame_end = 1, 20


def shot_label_macro(scn):
    """Raking close-up of the label typography through the glass."""
    studio_dark()
    build_bottle()
    c = camera((0.42, -0.95, 0.72), (0.0, -0.28, 0.62), lens=105, dof=0.82, fstop=2.0)
    key(c, 1, location=(0.46, -0.95, 0.70))
    key(c, 12, location=(0.34, -0.97, 0.74))
    ease_all("LINEAR")
    scn.frame_start, scn.frame_end = 1, 12


def shot_whip(scn):
    studio_dark()
    b = build_bottle()
    camera((0, -4.3, 1.0), (0, 0, 0.82), lens=65)
    key(b, 1, rotation_euler=(0, 0, math.radians(-150)))
    key(b, 15, rotation_euler=(0, 0, math.radians(0)))
    for fc in bpy.data.actions[0].fcurves if hasattr(bpy.data.actions[0], "fcurves") else []:
        for kp in fc.keyframe_points:
            kp.interpolation = "EXPO"
            kp.easing = "EASE_OUT"
    scn.frame_start, scn.frame_end = 1, 15


def shot_sweep(scn):
    """Silhouette in the dark: a single light passes and reveals the shape."""
    world((0, 0, 0), 0)
    sweep()
    build_bottle()
    l = area("pass", (-3, -2.2, 1.2), (0, 0, 0.8), 0.35, 420, (1.0, 0.85, 0.7), size_y=3.5)
    rim = area("rim", (0, 2.4, 2.0), (0, 0, 0.8), 1.0, 90, (1.0, 0.7, 0.45))
    st = strip("passStrip", (-2.0, -1.6, 0.9), (0, 0, 0.8), 0.22, 3.0, 16)
    camera((0, -4.0, 0.95), (0, 0, 0.8), lens=60)
    key(l, 1, location=(-3.2, -2.2, 1.2))
    key(l, 30, location=(3.2, -2.2, 1.2))
    key(st, 1, location=(-2.4, -1.4, 0.9))
    key(st, 30, location=(2.4, -1.4, 0.9))
    for o in (l, st):
        look_at(o, (0, 0, 0.8))
    scn.frame_start, scn.frame_end = 1, 30


# Brand palette (matches the halfsecond profile picture), linear RGB for Blender.
BRAND_ORANGE = (1.0, 0.074, 0.016)   # #FF4D22
BRAND_BONE = (0.871, 0.815, 0.723)   # #F0E9DD


def shot_hero(scn):
    """Slow turntable on a brand-coloured sweep — the colour hero.

    HERO_BG=orange (default) or bone picks the backdrop.
    """
    bg = os.environ.get("HERO_BG", "orange")
    world((0.0, 0.0, 0.0), 0)
    if bg == "bone":
        sweep(tuple(c * 0.55 for c in BRAND_BONE), rough=0.45)
        back = (1.0, 0.35, 0.12)
    else:
        sweep(BRAND_ORANGE, rough=0.22, floor=(0.006, 0.0055, 0.005))
        back = (1.0, 0.75, 0.6)
    b = build_bottle()
    area("key", (-2.6, -2.6, 2.8), (0, 0, 0.7), 1.8, 300, (1.0, 0.92, 0.84))
    area("fill", (2.8, -2.0, 1.2), (0, 0, 0.7), 2.5, 70, (1.0, 0.95, 0.9))
    area("rimL", (-2.0, 1.8, 1.6), (0, 0, 0.8), 0.6, 300, (1.0, 0.95, 0.9), size_y=3.0)
    area("rimR", (2.0, 1.8, 1.6), (0, 0, 0.8), 0.6, 240, (1.0, 0.95, 0.9), size_y=3.0)
    area("backlight", (0, 3.5, 1.5), (0, 12, 2.0), 3.5, 1100, back)
    strip("stripL", (-1.6, -1.4, 0.9), (0, 0, 0.8), 0.25, 3.0, 12)
    strip("stripR", (1.7, -1.0, 0.9), (0, 0, 0.8), 0.18, 3.0, 8)
    # Framed low so the top third stays clean for the title/offer typography.
    c = camera((0, -5.2, 1.23), (0, 0, 1.23), lens=48, dof=5.0, fstop=4.0)
    key(b, 1, rotation_euler=(0, 0, math.radians(-28)))
    # Rendered on twos (45 frames); compose.py blends between them for 105 programme frames.
    key(b, 45, rotation_euler=(0, 0, math.radians(8)))
    key(c, 1, location=(0, -5.25, 1.23))
    key(c, 45, location=(0, -4.85, 1.23))
    ease_all("LINEAR")
    scn.frame_start, scn.frame_end = 1, 45


def shot_drop(scn):
    """Bottle drops into frame and lands with a tiny settle."""
    studio_dark()
    b = build_bottle()
    camera((0, -3.9, 0.55), (0, 0, 0.75), lens=55)
    key(b, 1, location=(0, 0, 3.2), rotation_euler=(0, 0, math.radians(-20)))
    key(b, 7, location=(0, 0, 0.0), rotation_euler=(0, 0, math.radians(-4)))
    key(b, 10, location=(0, 0, 0.06), rotation_euler=(0, 0, math.radians(-2)))
    key(b, 13, location=(0, 0, 0.0), rotation_euler=(0, 0, 0))
    key(b, 15, location=(0, 0, 0.0), rotation_euler=(0, 0, 0))
    scn.frame_start, scn.frame_end = 1, 15


def shot_thumb(scn):
    """A clay-like thumb sprite (nail side up) on transparent background for the scroll gag."""
    world((1, 1, 1), 0.25)
    skin = mat_principled("skin", (0.62, 0.38, 0.27), rough=0.5)
    bsdf = skin.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Subsurface Weight"].default_value = 0.4
    bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.35, 0.2)
    bsdf.inputs["Subsurface Scale"].default_value = 0.1
    nail = mat_principled("nail", (0.78, 0.55, 0.5), rough=0.2, coat=0.8)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location=(0, 0, 0), segments=64, ring_count=32)
    t = bpy.context.object
    t.scale = (1.05, 2.2, 0.7)
    bpy.ops.object.transform_apply(scale=True)
    for v in t.data.vertices:
        if v.co.y < 0:
            v.co.y *= 2.6
            v.co.x *= 1.0 + min(-v.co.y, 3.0) * 0.06
    t.modifiers.new("ss", "SUBSURF").levels = 2
    bpy.ops.object.shade_smooth()
    t.data.materials.append(skin)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location=(0, 1.0, 0.5), segments=48, ring_count=24)
    n = bpy.context.object
    n.scale = (0.72, 1.0, 0.18)
    n.data.materials.append(nail)
    bpy.ops.object.shade_smooth()
    for o in (t, n):
        o.rotation_euler = (0, 0, math.radians(24))
    area("k", (-3, 3, 6), (0, 0, 0), 4, 380, (1.0, 0.93, 0.85))
    area("f", (3, -2, 4), (0, 0, 0), 5, 90)
    bpy.ops.object.camera_add(location=(0, 0, 12))
    c = bpy.context.object
    c.data.type = "ORTHO"
    c.data.ortho_scale = 9
    scn.camera = c
    scn.render.film_transparent = True
    scn.frame_start = scn.frame_end = 1


SHOTS = {
    "boring": shot_boring,
    "glass_macro": shot_glass_macro,
    "cap_macro": shot_cap_macro,
    "label_macro": shot_label_macro,
    "whip": shot_whip,
    "sweep": shot_sweep,
    "hero": shot_hero,
    "drop": shot_drop,
    "thumb": shot_thumb,
}


def main():
    args = sys.argv[1:]
    shot = args[0]
    res = "1080x1920"
    samples = 48
    frames = None
    for i, a in enumerate(args):
        if a == "--res":
            res = args[i + 1]
        if a == "--samples":
            samples = int(args[i + 1])
        if a == "--frames":
            frames = [int(x) for x in args[i + 1].split("-")]
    reset()
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    scn.cycles.samples = samples
    scn.cycles.use_adaptive_sampling = True
    scn.cycles.use_denoising = True
    scn.cycles.max_bounces = 16
    scn.cycles.transmission_bounces = 16
    scn.cycles.glossy_bounces = 8
    scn.cycles.volume_bounces = 2
    scn.cycles.caustics_reflective = False
    scn.cycles.caustics_refractive = True
    scn.cycles.blur_glossy = 0.6
    w, h = (int(x) for x in res.split("x"))
    scn.render.resolution_x, scn.render.resolution_y = w, h
    scn.render.fps = 30
    scn.render.motion_blur_shutter = 0.5
    scn.render.image_settings.file_format = "PNG"
    scn.render.image_settings.color_mode = "RGBA"
    try:
        scn.view_settings.view_transform = "AgX"
        scn.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    SHOTS[shot](scn)
    scn.render.use_motion_blur = shot in ("whip", "drop")
    if shot == "thumb":
        scn.render.resolution_x, scn.render.resolution_y = 900, 1400
    if frames:
        scn.frame_start, scn.frame_end = frames
    out = os.environ.get("OUTNAME", shot)
    os.makedirs(os.path.join(OUT, out), exist_ok=True)
    scn.render.filepath = os.path.join(OUT, out, "####")
    bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    main()
