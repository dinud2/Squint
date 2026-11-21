"""Squint demo rig: a bathroom medicine cabinet with a Logitech C270 under it, built in Blender from code.

    blender -b -P rig/build_rig.py

Units are millimetres (1 Blender unit = 1 mm, so the STL comes out in mm).
Axes: x to the right as the camera sees it, y out of the wall into the room, z up from the floor.

    wall | medicine cabinet (mirror door open, shelves of bottles)
         |   C270 in a printed mount under the cabinet, tilted up a little
         | pedestal sink                      bath mat, Margaret standing ~1 m from the lens

Why she stands ~1 m back: the C270 is a narrow webcam (55 deg diagonal, about 49 x 29 deg at the
960x544 stream). The intake model needs her nose, mouth, both shoulders and the hand on its way
to her mouth all in frame, and that only fits from about 1 m (it was trained for 0.9-1.4 m).

Outputs (next to this file):
    squint_rig.blend         the whole scene
    stl/c270_mount.stl       the only printed part
    renders/*.png            hero, cabinet close-up, side view with the camera's field of view, camera POV
"""
import math
import os

import bmesh
import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))

# ------------------------------------------------------------------ the numbers
# Logitech C270: 55 deg diagonal field of view (720p); camstream sends 960x544 @ 20 fps (pi/README.md).
IMG_W, IMG_H = 960, 544
_d = math.tan(math.radians(55 / 2)) / math.hypot(16, 9)
HFOV = 2 * math.degrees(math.atan(_d * 16))      # ~48.8 deg
VFOV = 2 * math.degrees(math.atan(_d * 9))       # ~28.6 deg
TILT = 5.0                                       # camera tilted up, degrees

C270 = dict(w=73, h=32, d=28, fit=0.8)           # camera body without its clip; measure yours and adjust
CABINET = dict(w=500, h=650, d=150, z=1300, t=15, shelves=(1300 + 210, 1300 + 420))
SINK = dict(w=520, d=420, h=850)
PERSON_Y = 1330                                  # her body centre; face ~1.05 m from the lens
FLOOR_TO_HEAD = 1600                             # Margaret is 1.60 m


# ------------------------------------------------------------------ helpers
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    s = bpy.context.scene
    s.unit_settings.system = "METRIC"
    s.unit_settings.scale_length = 0.001
    s.unit_settings.length_unit = "MILLIMETERS"


MATS = {}


def mat(name, rgb):
    if name not in MATS:
        m = bpy.data.materials.new(name)
        m.diffuse_color = (*rgb, 1.0)
        MATS[name] = m
    return MATS[name]


def link(ob, m=None):
    bpy.context.scene.collection.objects.link(ob)
    if m is not None:
        ob.data.materials.append(m)
    return ob


def mesh_from_bm(name, bm, m=None):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return link(bpy.data.objects.new(name, me), m)


def box(name, sx, sy, sz, loc=(0, 0, 0), m=None):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    bmesh.ops.translate(bm, vec=loc, verts=bm.verts)
    return mesh_from_bm(name, bm, m)


def cyl(name, r, h, loc=(0, 0, 0), m=None, segs=48):
    """Cylinder along z, centred on loc."""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=r, radius2=r, depth=h)
    bmesh.ops.translate(bm, vec=loc, verts=bm.verts)
    return mesh_from_bm(name, bm, m)


def sphere(name, r, loc, m=None):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=r)
    bmesh.ops.translate(bm, vec=loc, verts=bm.verts)
    return mesh_from_bm(name, bm, m)


def between(ob, a, b):
    """Point a z-aligned object from a to b."""
    a, b = Vector(a), Vector(b)
    ob.matrix_world = Matrix.Translation((a + b) / 2) @ (b - a).to_track_quat("Z", "Y").to_matrix().to_4x4()
    return ob


def limb(name, a, b, r, m):
    """Capsule from point a to point b."""
    between(cyl(name, r, (Vector(b) - Vector(a)).length, m=m, segs=24), a, b)
    sphere(name + "_j1", r, a, m)
    sphere(name + "_j2", r, b, m)


def boolean(target, cutters, op="DIFFERENCE"):
    """Apply booleans for real and delete the cutters, so the STL is a plain solid."""
    for c in cutters:
        mod = target.modifiers.new("b", "BOOLEAN")
        mod.object, mod.operation, mod.solver = c, op, "EXACT"
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(target.evaluated_get(dg))
    target.modifiers.clear()
    target.data = me
    for c in cutters:
        bpy.data.objects.remove(c)
    return target


# ------------------------------------------------------------------ the printed part
def make_mount(m):
    """C270 mount, in print orientation: local z = 0 is the underside of the cabinet, y = 0 its front edge.

    A plate screws to the cabinet's underside (2 wood screws). In front of it hangs a sleeve the C270 body
    slides into from the back, already tilted TILT degrees up. The lens looks through a window in the
    front wall; a zip tie through the two slots holds the camera in. Fold the C270's clip flat against
    its back first (or take it off).
    """
    w, h, d, fit = C270["w"] + 2 * C270["fit"], C270["h"] + 2 * C270["fit"], C270["d"], C270["fit"]
    wall = 3.0
    ow, oh, od = w + 2 * wall, h + 2 * wall, d + wall
    plate = box("c270_mount", ow + 20, 70, 5, (0, -30, -2.5), m)
    # sleeve centre: in front of the cabinet edge, hanging just below it
    c = Vector((0, od / 2 + 2, -oh / 2 - 9))
    R = Matrix.Translation(c) @ Matrix.Rotation(math.radians(TILT), 4, "X")

    def local(name, sx, sy, sz, at=(0, 0, 0)):
        ob = box(name, sx, sy, sz)
        ob.matrix_world = R @ Matrix.Translation(at)
        return ob

    sleeve = local("sleeve", ow, od, oh)
    web = box("web", ow, 14, 12, (0, 4, -6))                       # joins the sleeve to the plate
    boolean(plate, [sleeve, web], "UNION")
    cut = [
        local("c_pocket", w, d + 10, h, (0, -wall / 2 - 5, 0)),    # open at the back
        local("c_lens", 30, 20, 22, (0, od / 2, 0)),               # window for the lens (centre of the C270 bar)
        local("c_tie_l", 4, 8, oh + 10, (-w / 2 + 8, -od / 2 + 8, 0)),
        local("c_tie_r", 4, 8, oh + 10, (w / 2 - 8, -od / 2 + 8, 0)),
        cyl("c_screw_l", 2.2, 20, (-ow / 2 + 2, -45, 0), segs=16),
        cyl("c_screw_r", 2.2, 20, (ow / 2 - 2, -45, 0), segs=16),
        box("c_cable", 14, 30, 8, (ow / 2 - 4, -10, -4)),           # USB cable leaves toward the side
    ]
    boolean(plate, cut)
    lens = R @ Vector((0, od / 2, 0))                               # lens sits at the front wall
    return plate, lens


# ------------------------------------------------------------------ the set (not printed)
def scene_props():
    M = {k: mat(k, c) for k, c in dict(
        wall=(0.86, 0.89, 0.88), tile=(0.93, 0.94, 0.95), floor=(0.62, 0.6, 0.58), cab=(0.97, 0.97, 0.96),
        mirror=(0.72, 0.84, 0.9), porcelain=(0.98, 0.98, 0.98), chrome=(0.7, 0.72, 0.75), mat=(0.45, 0.62, 0.6),
        amber=(0.62, 0.28, 0.04), black=(0.05, 0.05, 0.06), white=(0.93, 0.93, 0.92), red=(0.8, 0.1, 0.1),
        blue=(0.15, 0.3, 0.7), green=(0.2, 0.55, 0.3), light=(1.0, 0.97, 0.85), towel=(0.55, 0.7, 0.85),
        skin=(0.85, 0.66, 0.52), shirt=(0.52, 0.48, 0.74), pants=(0.28, 0.29, 0.38), hair=(0.82, 0.82, 0.84),
        shoe=(0.2, 0.15, 0.12)).items()}

    box("wall", 3000, 20, 2600, (0, -10, 1300), M["wall"])
    box("tile_splash", 900, 4, 450, (0, 2, 850 + 225), M["tile"])
    box("floor", 3000, 3000, 20, (0, 1500, -10), M["floor"])
    box("bath_mat", 800, 550, 8, (0, PERSON_Y - 30, 4), M["mat"])

    # pedestal sink
    sw, sd, sh = SINK["w"], SINK["d"], SINK["h"]
    cyl("sink_pedestal", 110, sh - 120, (0, 200, (sh - 120) / 2), M["porcelain"])
    box("sink_bowl", sw, sd, 160, (0, sd / 2, sh - 80), M["porcelain"])
    box("sink_basin", sw - 90, sd - 120, 30, (0, sd / 2 + 20, sh - 10), M["chrome"])
    cyl("faucet", 14, 120, (0, 50, sh + 60), M["chrome"])
    between(cyl("spout", 11, 110, m=M["chrome"]), (0, 50, sh + 115), (0, 150, sh + 100))

    # medicine cabinet: open box against the wall, two glass shelves, mirror door swung open
    w, h, d, z0, t = CABINET["w"], CABINET["h"], CABINET["d"], CABINET["z"], CABINET["t"]
    box("cab_back", w, t, h, (0, t / 2, z0 + h / 2), M["cab"])
    for sx in (-1, 1):
        box(f"cab_side{sx}", t, d, h, (sx * (w - t) / 2, d / 2, z0 + h / 2), M["cab"])
    box("cab_top", w, d, t, (0, d / 2, z0 + h - t / 2), M["cab"])
    box("cab_bottom", w, d, t, (0, d / 2, z0 + t / 2), M["cab"])
    for i, sz in enumerate(CABINET["shelves"]):
        box(f"cab_shelf{i}", w - 2 * t, d - 20, 6, (0, (d - 20) / 2 + t, sz), M["mirror"])
    door = box("cab_mirror_door", w, 20, h, (w / 2, 10, h / 2), M["mirror"])
    door.matrix_world = Matrix.Translation((-w / 2, d, z0)) @ Matrix.Rotation(math.radians(105), 4, "Z")
    box("vanity_light", w - 60, 60, 60, (0, 60, z0 + h + 80), M["light"])
    box("towel_bar", 10, 60, 10, (520, 30, 1150), M["chrome"])
    box("towel", 380, 30, 520, (520, 60, 900), M["towel"])

    # bottles on the shelves (the omega-3 bottle is in her hand, so its spot is empty)
    def bottle(name, x, y, z, r, hh, body, cap):
        cyl(name, r, hh, (x, y, z + hh / 2), M[body])
        cyl(name + "_label", r + 0.5, hh * 0.5, (x, y, z + hh * 0.45), M["white"])
        cyl(name + "_cap", r + 1.5, 14, (x, y, z + hh + 7), M[cap])

    s0, s1, fl = CABINET["shelves"][0] + 3, CABINET["shelves"][1] + 3, z0 + t
    bottle("tylenol", -150, 75, fl, 28, 105, "white", "red")
    bottle("vial_a", -60, 75, fl, 20, 70, "amber", "white")
    bottle("vial_b", 10, 75, fl, 20, 70, "amber", "white")
    bottle("vitamin_d", 150, 75, fl, 26, 120, "green", "white")
    bottle("vial_c", -140, 75, s0, 20, 70, "amber", "white")
    bottle("allergy", 130, 75, s0, 24, 90, "blue", "white")
    bottle("vial_d", -40, 75, s1, 18, 60, "amber", "white")
    bottle("aspirin", 100, 75, s1, 24, 85, "white", "blue")

    # Margaret standing on the mat, facing the cabinet (-y). Her right is -x.
    y = PERSON_Y
    k = FLOOR_TO_HEAD / 1600
    zs, zh = 1320 * k, 1500 * k                                   # shoulders, head centre
    for sx in (-1, 1):
        box(f"shoe{sx}", 90, 250, 70, (sx * 95, y - 50, 35), M["shoe"])
        limb(f"shin{sx}", (sx * 95, y, 80), (sx * 95, y, 480 * k), 55, M["pants"])
        limb(f"thigh{sx}", (sx * 95, y, 480 * k), (sx * 90, y, 880 * k), 70, M["pants"])
    limb("torso", (0, y, 950 * k), (0, y, 1220 * k), 145, M["shirt"])
    limb("neck", (0, y, 1360 * k), (0, y - 5, 1420 * k), 45, M["skin"])
    sphere("head", 95, (0, y - 5, zh), M["skin"])
    sphere("hair", 99, (0, y + 8, zh + 20), M["hair"])
    sh_r, sh_l = (-175, y, zs), (175, y, zs)
    elbow_r, hand_r = (-215, y - 150, 1060 * k), (-75, y - 170, 1400 * k)
    limb("arm_r_upper", sh_r, elbow_r, 42, M["shirt"])
    limb("arm_r_fore", elbow_r, hand_r, 34, M["skin"])
    limb("arm_l_upper", sh_l, (205, y - 20, 1030 * k), 42, M["shirt"])
    limb("arm_l_fore", (205, y - 20, 1030 * k), (190, y - 70, 790 * k), 34, M["skin"])
    sphere("hand_r", 42, hand_r, M["skin"])
    sphere("hand_l", 40, (190, y - 75, 760 * k), M["skin"])
    # the omega-3 bottle, tipped toward her mouth
    hb = Vector(hand_r) + Vector((10, -25, 20))
    tip = Matrix.Translation(hb) @ Matrix.Rotation(math.radians(-40), 4, "X")
    for name, r, hh, mm, dz in (("omega369", 30, 100, "black", 0), ("omega369_cap", 31.5, 14, "white", 57)):
        o = cyl(name, r, hh, m=M[mm])
        o.matrix_world = tip @ Matrix.Translation((0, 0, dz))

    face = y - 5 - 95
    return {
        "nose": (0, face, zh), "mouth": (0, face + 8, zh - 40 * k), "eye_l": (35, face + 15, zh + 25),
        "eye_r": (-35, face + 15, zh + 25), "shoulder_l": sh_l, "shoulder_r": sh_r,
        "hand_at_mouth": hand_r, "hand_at_chest": (-70, y - 260, 1180 * k),
        "head_top (nice to have)": (0, y, zh + 95), "hip (nice to have)": (0, y, 900 * k),
    }


# ------------------------------------------------------------------ cameras and views
def c270_camera(lens):
    cd = bpy.data.cameras.new("c270")
    cd.sensor_fit = "HORIZONTAL"
    cd.angle = math.radians(HFOV)
    cd.clip_start, cd.clip_end = 5, 10000
    cam = link(bpy.data.objects.new("c270", cd))
    cam.location = lens
    cam.rotation_euler = (math.radians(90 + TILT), 0, 0)        # look along +y, tilted up
    return cam


def frustum(cam, dist, m):
    """Orange rods along the edges of what the camera sees, for the side-view render."""
    s = bpy.context.scene
    s.render.resolution_x, s.render.resolution_y = IMG_W, IMG_H
    bpy.context.view_layer.update()
    mw = cam.matrix_world
    apex = mw.translation
    ends = [mw @ (c * (dist / -c.z)) for c in cam.data.view_frame(scene=s)]
    rods = []
    for i in range(4):
        for a, b in ((apex, ends[i]), (ends[i], ends[(i + 1) % 4])):
            rods.append(between(cyl(f"view_cone_{len(rods)}", 4, (b - a).length, m=m, segs=8), a, b))
    return rods


def view_cam(name, loc, target, lens=35, ortho=None):
    cd = bpy.data.cameras.new(name)
    cd.clip_start, cd.clip_end = 5, 20000
    if ortho:
        cd.type, cd.ortho_scale = "ORTHO", ortho
    else:
        cd.lens = lens
    cam = link(bpy.data.objects.new(name, cd))
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return cam


def render(cam, path, w, h, hide=()):
    s = bpy.context.scene
    s.camera = cam
    s.render.resolution_x, s.render.resolution_y, s.render.resolution_percentage = w, h, 100
    for o in hide:
        o.hide_render = True
    s.render.filepath = path
    bpy.ops.render.render(write_still=True)
    for o in hide:
        o.hide_render = False


def setup_render():
    s = bpy.context.scene
    s.render.engine = "BLENDER_WORKBENCH"
    sh = s.display.shading
    sh.light, sh.color_type = "STUDIO", "MATERIAL"
    sh.show_shadows, sh.show_cavity, sh.show_object_outline = False, True, True   # shadows turn the room black
    s.world = bpy.data.worlds.new("w")
    s.world.color = (0.94, 0.95, 0.97)
    s.render.image_settings.file_format = "PNG"


# ------------------------------------------------------------------ checks and export
def project(cam, p):
    s = bpy.context.scene
    s.render.resolution_x, s.render.resolution_y = IMG_W, IMG_H
    v = world_to_camera_view(s, cam, Vector(p))
    return v.x * IMG_W, (1 - v.y) * IMG_H, v.z


def non_manifold(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    n = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    return n


def export_stl(ob, path):
    mw = ob.matrix_world.copy()
    ob.matrix_world = Matrix.Rotation(math.radians(180), 4, "X")  # flip: plate on the bed, sleeve up
    for o in bpy.context.scene.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True, apply_modifiers=True)
    ob.matrix_world = mw


def main():
    reset()
    setup_render()
    mount, lens_local = make_mount(mat("print_grey", (0.35, 0.36, 0.38)))
    # place it under the cabinet's front edge, centred
    mount.location = (0, CABINET["d"], CABINET["z"])
    bpy.context.view_layer.update()
    lens = mount.matrix_world @ lens_local
    body = scene_props()
    box("c270_body", C270["w"], C270["d"], C270["h"], m=mat("black", (0.05, 0.05, 0.06))).matrix_world = \
        mount.matrix_world @ Matrix.Translation(lens_local) @ Matrix.Rotation(math.radians(TILT), 4, "X") \
        @ Matrix.Translation((0, -C270["d"] / 2 - 1, 0))

    cam = c270_camera(lens)
    cone = frustum(cam, 1600, mat("cone", (1.0, 0.45, 0.0)))

    print(f"\n[rig] C270 at {IMG_W}x{IMG_H}: HFOV {HFOV:.1f} deg, VFOV {VFOV:.1f} deg, tilted up {TILT} deg")
    print(f"[rig] lens at z={lens.z:.0f} mm (floor), y={lens.y:.0f}; her face is {body['nose'][1] - lens.y:.0f} mm away")
    ok = True
    for k, p in body.items():
        x, y, z = project(cam, p)
        inside = 0 <= x <= IMG_W and 0 <= y <= IMG_H and z > 0
        margin = min(x, IMG_W - x, y, IMG_H - y)
        print(f"  {k:24s} x={x:4.0f} y={y:4.0f}  {'in view' if inside else 'OUT OF VIEW'}  (edge margin {margin:4.0f} px)")
        if "nice" not in k and not inside:
            ok = False

    os.makedirs(os.path.join(HERE, "stl"), exist_ok=True)
    d = mount.dimensions
    print(f"[rig] c270_mount {d.x:.0f} x {d.y:.0f} x {d.z:.0f} mm, non-manifold edges: {non_manifold(mount)}")
    export_stl(mount, os.path.join(HERE, "stl", "c270_mount.stl"))

    rd = os.path.join(HERE, "renders")
    os.makedirs(rd, exist_ok=True)
    render(view_cam("v_hero", (1900, 2900, 1750), (0, 600, 1200), lens=32), os.path.join(rd, "hero.png"), 1600, 1000)   # with the view cone
    render(view_cam("v_cabinet", (650, 900, 1250), (0, 120, 1400), lens=30), os.path.join(rd, "cabinet.png"), 1600, 1000, hide=cone)
    render(view_cam("v_mount", (230, 420, 1180), tuple(lens), lens=50), os.path.join(rd, "c270_mount.png"), 1200, 800, hide=cone)
    render(view_cam("v_side", (3200, 800, 1150), (0, 800, 1150), ortho=2500), os.path.join(rd, "side_fov.png"), 1600, 1000)
    render(cam, os.path.join(rd, "camera_pov.png"), IMG_W, IMG_H, hide=cone)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "squint_rig.blend"))
    print("[rig] all must-see points in view:", ok)


main()
