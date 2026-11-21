"""Squint station rig, built in Blender from code so every number is in one place.

    blender -b -P rig/build_rig.py

Units are millimetres (1 Blender unit = 1 mm, so the STLs come out in mm).
Axes: x to the right as the camera sees it, y away from the camera toward Margaret, z up.
z = 0 is the top of the foam-board baseplate that everything is glued to.

Layout, side view (camera looks along +y, toward Margaret):

    camera head ─┐ ~285 mm up, tilted 6 deg down
    tower        │
    [ base: Pi, LCD, speaker ]   [ shelf: 3 slots ]   [ NFC + button pod ]          Margaret, ~1.1 m away
    y = -150 .. 0                y = 365 .. 465       y = 505 .. 575

The idea: the camera sits BEHIND the bottles. Each bottle lives in its own slot, so when a
slot goes empty we know which bottle she picked up, without ever seeing its label. The same
camera still sees her head, shoulders and hands for the intake model.

Outputs (next to this file):
    squint_rig.blend            the whole scene
    stl/*.stl                   printable parts, each in its own print orientation
    renders/*.png               hero, side view with the camera's field of view, camera POV
    slots_default.json          where each slot lands in the 640x480 camera image
"""
import json
import math
import os

import bmesh
import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))

# ------------------------------------------------------------------ the numbers
# Camera: Pi Camera Module 3, standard lens, streamed at 640x480. Same intrinsics as
# vision/sim/pose_sim.py (F = 493 px), so the POV render matches what the models were tuned on.
IMG_W, IMG_H, F_PX = 640, 480, 493.0
HFOV = 2 * math.degrees(math.atan(IMG_W / 2 / F_PX))      # ~66 deg
CAM_TILT = 6.0                 # degrees down
BASE = dict(w=240, d=150, h=70, wall=3)
BASE_Y = -75                   # base centre (front face at y = 0)
TOWER = dict(w=40, h=180, channel=18, flange=70)
TOWER_Y = -110                 # tower centre
WEDGE = dict(w=40, front=6)    # tilt adapter between tower and head
HEAD = dict(w=48, d=30, h=44, wall=2.5, lens_z=28)
SHELF = dict(w=240, d=100, h=24, depth=16, y=415)
SLOTS = [  # x position, pocket diameter, what lives there in the demo
    dict(slot=1, x=-75, dia=66, med="omega369 (stand-in for warfarin)"),
    dict(slot=2, x=0, dia=46, med="metoprolol_robert (look-alike)"),
    dict(slot=3, x=75, dia=46, med="atorvastatin"),
]
POD = dict(w=110, d=70, h=32, y=540, button=30, nfc=50)
BOARD = dict(w=300, y0=-170, y1=590, t=5)
MARGARET_Y = 1010              # head centre; ~1.1 m from the camera (sim trains 0.9-1.4 m)


# ------------------------------------------------------------------ helpers
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    s = bpy.context.scene
    s.unit_settings.system = "METRIC"
    s.unit_settings.scale_length = 0.001
    s.unit_settings.length_unit = "MILLIMETERS"


MATS = {}


def mat(name, rgb, alpha=1.0):
    if name not in MATS:
        m = bpy.data.materials.new(name)
        m.diffuse_color = (*rgb, alpha)
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


def cyl(name, r, h, loc=(0, 0, 0), m=None, segs=64, r2=None):
    """Cylinder along z, centred on loc."""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=r, radius2=r if r2 is None else r2, depth=h)
    bmesh.ops.translate(bm, vec=loc, verts=bm.verts)
    return mesh_from_bm(name, bm, m)


def sphere(name, r, loc, m=None):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=r)
    bmesh.ops.translate(bm, vec=loc, verts=bm.verts)
    return mesh_from_bm(name, bm, m)


def limb(name, a, b, r, m):
    """Capsule from point a to point b."""
    a, b = Vector(a), Vector(b)
    ob = cyl(name, r, (b - a).length, m=m, segs=24)
    ob.matrix_world = Matrix.Translation((a + b) / 2) @ (b - a).to_track_quat("Z", "Y").to_matrix().to_4x4()
    sphere(name + "_j1", r, a, m)
    sphere(name + "_j2", r, b, m)
    return ob


def text_mesh(name, s, size, depth):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body, cu.size, cu.extrude = s, size, depth / 2
    cu.align_x, cu.align_y = "CENTER", "CENTER"
    tob = link(bpy.data.objects.new(name + "_t", cu))
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(tob.evaluated_get(dg))
    bpy.data.objects.remove(tob)
    return link(bpy.data.objects.new(name, me))


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


def wedge(name, w, d, h_front, h_back, m=None):
    """Block whose top slopes down toward +y (the camera side faces Margaret)."""
    bm = bmesh.new()
    x, y = w / 2, d / 2
    v = [bm.verts.new(p) for p in [(-x, -y, 0), (x, -y, 0), (x, y, 0), (-x, y, 0),
                                   (-x, -y, h_back), (x, -y, h_back), (x, y, h_front), (-x, y, h_front)]]
    for f in [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]:
        bm.faces.new([v[i] for i in f])
    return mesh_from_bm(name, bm, m)


# ------------------------------------------------------------------ printable parts
# Each part is built around its own origin in its print orientation, then placed in the scene.
PARTS = {}


def part(ob, loc, rot=(0, 0, 0)):
    PARTS[ob.name] = ob
    ob.location = loc
    ob.rotation_euler = [math.radians(a) for a in rot]
    return ob


def make_base(m):
    w, d, h, t = BASE["w"], BASE["d"], BASE["h"], BASE["wall"]
    ob = box("base", w, d, h, (0, 0, h / 2), m)
    cut = [box("c_in", w - 2 * t, d - 2 * t, h - t + 1, (0, 0, (h - t + 1) / 2 - 1))]       # hollow, open bottom
    cut.append(box("c_lcd", 72, 10, 26, (-55, d / 2, 40)))                                  # 16x2 LCD window, faces Margaret
    for i in range(7):                                                                       # speaker grille on top
        for j in range(5):
            cut.append(cyl("c_spk", 2, 10, (45 + i * 9, 10 + j * 9, h), segs=16))
    ty = TOWER_Y - BASE_Y
    cut.append(box("c_cable_up", TOWER["channel"], TOWER["channel"], 10, (0, ty, h)))      # camera ribbon goes up the tower
    for sx in (-1, 1):
        for sy in (-1, 1):
            cut.append(cyl("c_m3", 1.6, 10, (sx * 27, ty + sy * 27, h), segs=16))          # tower flange screws
    cut.append(box("c_power", 30, 10, 16, (40, -d / 2, 12)))                                # USB-C + Ethernet out the back
    return boolean(ob, cut)


def make_tower(m):
    w, h, ch, fl = TOWER["w"], TOWER["h"], TOWER["channel"], TOWER["flange"]
    ob = box("tower", w, w, h, (0, 0, h / 2), m)
    foot = box("foot", fl, fl, 4, (0, 0, 2), m)
    boolean(ob, [foot], "UNION")
    cut = [box("c_ch", ch, ch, h + 2, (0, 0, h / 2))]
    for sx in (-1, 1):
        for sy in (-1, 1):
            cut.append(cyl("c_m3", 1.6, 10, (sx * 27, sy * 27, 2), segs=16))
    # a slot on the face toward Margaret lets the ribbon cable out near the top if you prefer
    return boolean(ob, cut)


def make_wedge(m):
    w = WEDGE["w"]
    hb = WEDGE["front"] + w * math.tan(math.radians(CAM_TILT))
    ob = wedge(f"tilt_wedge_{CAM_TILT:.0f}deg", w, w, WEDGE["front"], hb, m)
    return boolean(ob, [box("c_ch", TOWER["channel"], TOWER["channel"], 40, (0, 0, 10))])


def make_head(m):
    w, d, h, t = HEAD["w"], HEAD["d"], HEAD["h"], HEAD["wall"]
    ob = box("camera_head", w, d, h, (0, 0, h / 2), m)
    lz = HEAD["lens_z"]
    cut = [
        box("c_in", w - 2 * t, d - 2 * t, h - 2 * t, (0, 0, h / 2)),                         # hollow
        box("c_back", w - 2 * t, 10, h - 2 * t, (0, -d / 2, h / 2)),                         # open back: slide the camera in
        cyl("c_lens", 5.5, 10, (0, d / 2, lz), segs=48),                                     # lens hole (CM3 lens ~ 8 mm)
        box("c_led", 34, 10, 5, (0, d / 2, 9)),                                              # slot for a small LED bar (light her face)
        box("c_cable", TOWER["channel"], TOWER["channel"], 10, (0, 0, 0)),                   # ribbon from the tower
    ]
    # Camera Module 3 board is 25 x 24 mm, M2 holes 21 mm x 12.5 mm apart, lens 9.4 mm above the bottom holes
    for sx in (-1, 1):
        for sz in (0, 1):
            cut.append(box("c_m2", 2.2, 10, 2.2, (sx * 10.5, d / 2, lz - 9.4 + 2.2 + sz * 12.5)))
    return boolean(ob, cut)


def make_shelf(m):
    w, d, h, dep = SHELF["w"], SHELF["d"], SHELF["h"], SHELF["depth"]
    ob = box("shelf", w, d, h, (0, 0, h / 2), m)
    cut = []
    for s in SLOTS:
        cut.append(cyl(f"c_pocket{s['slot']}", s["dia"] / 2, dep + 1, (s["x"], -5, h - dep / 2 + 0.5), segs=96))
        n = text_mesh(f"c_num{s['slot']}", str(s["slot"]), 14, 1.6)           # slot number on the face she sees
        n.matrix_world = Matrix.Translation((s["x"], d / 2, h / 2)) @ Matrix.Rotation(math.radians(90), 4, "X") \
            @ Matrix.Rotation(math.radians(180), 4, "Y")
        cut.append(n)
    return boolean(ob, cut)


def make_pod(m):
    w, d, h = POD["w"], POD["d"], POD["h"]
    ob = box("nfc_button_pod", w, d, h, (0, 0, h / 2), m)
    cut = [
        box("c_in", w - 6, d - 6, h - 2, (0, 0, (h - 2) / 2 - 1)),
        cyl("c_btn", POD["button"] / 2 + 0.2, 10, (28, 0, h), segs=64),            # 30 mm arcade button
        cyl("c_nfc", POD["nfc"] / 2, 2, (-25, 0, h), segs=64),                     # 1 mm dish marks the NFC tap spot
        box("c_wire", 20, 10, 10, (0, -d / 2, 5)),
    ]
    return boolean(ob, cut)


# ------------------------------------------------------------------ props (not printed)
def props():
    M = {k: mat(k, c) for k, c in dict(
        amber=(0.62, 0.28, 0.04), black=(0.05, 0.05, 0.06), white=(0.93, 0.93, 0.92), label=(0.97, 0.97, 0.95),
        yellow=(1.0, 0.85, 0.1), skin=(0.85, 0.66, 0.52), shirt=(0.52, 0.48, 0.74), pants=(0.28, 0.29, 0.38),
        hair=(0.82, 0.82, 0.84), wood=(0.55, 0.38, 0.25), board=(0.93, 0.92, 0.88), chair=(0.35, 0.25, 0.2),
        lcd=(0.15, 0.35, 0.55), red=(0.85, 0.12, 0.1), grey=(0.5, 0.5, 0.52)).items()}

    t = BOARD["t"]
    box("baseplate_foamboard", BOARD["w"], BOARD["y1"] - BOARD["y0"], t,
        (0, (BOARD["y0"] + BOARD["y1"]) / 2, -t / 2), M["board"])
    box("kitchen_table", 1600, 1130, 30, (0, 265, -t - 15), M["wood"])   # her edge at y = 830

    floor_z = SHELF["h"] - SHELF["depth"]
    for s in SLOTS:   # bright sticker on each pocket floor: an empty slot then shows a big yellow dot
        cyl(f"sticker{s['slot']}", s["dia"] / 2 - 4, 0.6, (s["x"], SHELF["y"] - 5, floor_z + 0.3), M["yellow"])

    def bottle(name, x, y, r, h, body, cap, z=floor_z):
        cyl(name, r, h, (x, y, z + h / 2), M[body])
        cyl(name + "_label", r + 0.4, h * 0.5, (x, y, z + h * 0.45), M["label"])
        cyl(name + "_cap", r + 1.5, 14, (x, y, z + h + 7), M[cap])

    bottle("omega369_bottle", SLOTS[0]["x"], SHELF["y"] - 5, 30, 100, "black", "white")
    bottle("atorvastatin_vial", SLOTS[2]["x"], SHELF["y"] - 5, 20, 68, "amber", "white")
    # slot 2 is empty in the scene: Robert's look-alike vial is in Margaret's hand, on its way to her mouth

    box("lcd_screen", 66, 1, 20, (BASE["w"] / 2 * 0 - 55, 1.2, 40), M["lcd"])
    cyl("button_cap", 14, 8, (28, POD["y"], POD["h"] + 4), M["red"])

    # Margaret, seated across the table, facing the camera (-y). Her right is -x.
    y0, tz = MARGARET_Y, -t - 30           # tz: table top is the board's underside
    seat = tz - 290
    box("chair_seat", 460, 440, 40, (0, y0 + 80, seat - 20), M["chair"])
    box("chair_back", 460, 40, 520, (0, y0 + 290, seat + 260), M["chair"])
    limb("torso", (0, y0 + 40, seat + 60), (0, y0 + 20, 205), 150, M["shirt"])
    limb("neck", (0, y0 + 20, 230), (0, y0 + 10, 290), 45, M["skin"])
    sphere("head", 95, (0, y0, 360), M["skin"])
    sphere("hair", 99, (0, y0 + 12, 380), M["hair"])
    sh_r, sh_l = (-185, y0 + 25, 215), (185, y0 + 25, 215)
    limb("arm_r_upper", sh_r, (-215, y0 - 80, -20), 42, M["shirt"])
    limb("arm_r_fore", (-215, y0 - 80, -20), (-70, y0 - 135, 270), 34, M["skin"])
    limb("arm_l_upper", sh_l, (215, y0 - 70, -40), 42, M["shirt"])
    limb("arm_l_fore", (215, y0 - 70, -40), (130, y0 - 300, 15), 32, M["skin"])
    sphere("hand_r", 42, (-55, y0 - 140, 290), M["skin"])
    sphere("hand_l", 40, (125, y0 - 320, 15), M["skin"])
    vial = cyl("robert_vial_in_hand", 20, 68, (-40, y0 - 160, 300), M["amber"])
    cap = cyl("robert_vial_cap", 21.5, 14, (-40, y0 - 160, 341), M["white"])
    for o in (vial, cap):   # tipped toward her mouth
        o.matrix_world = Matrix.Translation((-40, y0 - 160, 300)) @ Matrix.Rotation(math.radians(-35), 4, "X") \
            @ Matrix.Translation(-Vector((-40, y0 - 160, 300))) @ o.matrix_world
    for sx in (-1, 1):
        limb(f"thigh{sx}", (sx * 95, y0 + 60, seat + 40), (sx * 105, y0 - 330, seat + 50), 70, M["pants"])
        limb(f"shin{sx}", (sx * 105, y0 - 330, seat + 50), (sx * 110, y0 - 360, -760), 55, M["pants"])
    return {"mouth": (0, y0 - 88, 330), "nose": (0, y0 - 95, 360), "head_top": (0, y0, 465),
            "shoulder_l": sh_l, "shoulder_r": sh_r, "hand_r": (-55, y0 - 140, 290), "hand_l": (125, y0 - 320, 15),
            "hip": (0, y0 + 40, seat + 60)}


# ------------------------------------------------------------------ cameras and views
def squint_camera(head):
    """The real camera: lens centre of the camera head, tilted CAM_TILT down."""
    bpy.context.view_layer.update()
    lens = head.matrix_world @ Vector((0, HEAD["d"] / 2, HEAD["lens_z"]))
    cd = bpy.data.cameras.new("squint_cam")
    cd.sensor_fit = "HORIZONTAL"
    cd.angle = math.radians(HFOV)
    cd.clip_start, cd.clip_end = 5, 10000
    cam = link(bpy.data.objects.new("squint_cam", cd))
    cam.location = lens
    cam.rotation_euler = (math.radians(90 - CAM_TILT), 0, 0)
    return cam


def frustum(cam, dist, m):
    """Orange wireframe of what the camera sees, for the side-view render."""
    s = bpy.context.scene
    s.render.resolution_x, s.render.resolution_y = IMG_W, IMG_H
    bpy.context.view_layer.update()
    corners = [c * (dist / -c.z) for c in cam.data.view_frame(scene=s)]
    mw = cam.matrix_world
    apex, ends = mw.translation, [mw @ c for c in corners]
    rods = []
    for i in range(4):   # thin rods: the 4 edges of the view pyramid and the far rectangle
        for a, b in ((apex, ends[i]), (ends[i], ends[(i + 1) % 4])):
            r = cyl(f"view_cone_{len(rods)}", 3, (b - a).length, m=m, segs=8)
            r.matrix_world = Matrix.Translation((a + b) / 2) @ (b - a).to_track_quat("Z", "Y").to_matrix().to_4x4()
            rods.append(r)
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
    sh.show_shadows, sh.show_cavity, sh.show_object_outline = True, True, True
    s.display.shadow_focus = 0.5
    s.world = bpy.data.worlds.new("w")
    s.world.color = (0.94, 0.95, 0.97)
    s.render.image_settings.file_format = "PNG"


# ------------------------------------------------------------------ checks
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
    ob.matrix_world = Matrix.Identity(4)          # export in its own print orientation
    for o in bpy.context.scene.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True, apply_modifiers=True)
    ob.matrix_world = mw


# ------------------------------------------------------------------ main
def main():
    reset()
    setup_render()
    white = mat("print_white", (0.9, 0.9, 0.88))
    teal = mat("print_teal", (0.16, 0.5, 0.56))

    part(make_base(white), (0, BASE_Y, 0))
    part(make_tower(white), (0, TOWER_Y, BASE["h"]))
    wz = BASE["h"] + TOWER["h"]
    part(make_wedge(white), (0, TOWER_Y, wz))
    # head sits on the sloped top of the wedge: rotate about x by -tilt around the wedge's top centre
    mid_h = WEDGE["front"] + WEDGE["w"] / 2 * math.tan(math.radians(CAM_TILT))
    head = part(make_head(white), (0, TOWER_Y, wz + mid_h), (-CAM_TILT, 0, 0))
    part(make_shelf(teal), (0, SHELF["y"], 0))
    part(make_pod(teal), (0, POD["y"], 0))
    body = props()

    cam = squint_camera(head)
    cone = frustum(cam, 1400, mat("cone", (1.0, 0.45, 0.0)))

    # --- does the camera see what it must?
    rows, ok = [], True
    must = dict(body)
    floor_z = SHELF["h"] - SHELF["depth"]
    for s in SLOTS:
        must[f"slot{s['slot']}_floor"] = (s["x"], SHELF["y"] - 5, floor_z)
        must[f"slot{s['slot']}_cap_top"] = (s["x"], SHELF["y"] - 5, floor_z + 114)
    for k, p in must.items():
        x, y, z = project(cam, p)
        inside = 0 <= x <= IMG_W and 0 <= y <= IMG_H and z > 0
        rows.append((k, round(x), round(y), inside))
        if k not in ("hip",) and not inside:
            ok = False
    print("\n[rig] what the camera sees (640x480):")
    for k, x, y, inside in rows:
        print(f"  {k:18s} x={x:4d} y={y:4d}  {'in view' if inside else 'OUT OF VIEW'}")
    cx, cy, cz = cam.location
    print(f"[rig] camera lens at y={cy:.0f} z={cz:.0f} mm, tilt {CAM_TILT} deg down, HFOV {HFOV:.1f} deg")
    print(f"[rig] Margaret's face is {MARGARET_Y - 95 - cy:.0f} mm from the lens (sim trains 900-1400)")

    # --- where each slot lands in the image (for the slot detector)
    slots = []
    for s in SLOTS:
        pts = []
        r = s["dia"] / 2
        for zz in (floor_z, SHELF["h"]):
            for i in range(24):
                a = 2 * math.pi * i / 24
                pts.append(project(cam, (s["x"] + r * math.cos(a), SHELF["y"] - 5 + r * math.sin(a), zz)))
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        slots.append(dict(slot=s["slot"], med=s["med"], box=[round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys))]))
    with open(os.path.join(HERE, "slots_default.json"), "w") as f:
        json.dump(dict(image=[IMG_W, IMG_H], note="pixel boxes of each pocket in the camera image, from the CAD; "
                       "re-measure on the real rig", slots=slots), f, indent=2)
    print("[rig] slot boxes:", [s["box"] for s in slots])

    # --- printable parts
    os.makedirs(os.path.join(HERE, "stl"), exist_ok=True)
    print("[rig] parts:")
    for name, ob in PARTS.items():
        dims = ob.dimensions
        nm = non_manifold(ob)
        export_stl(ob, os.path.join(HERE, "stl", name + ".stl"))
        print(f"  {name:18s} {dims.x:5.0f} x {dims.y:5.0f} x {dims.z:5.0f} mm   non-manifold edges: {nm}")

    # --- renders
    rd = os.path.join(HERE, "renders")
    os.makedirs(rd, exist_ok=True)
    render(view_cam("v_hero", (1500, -900, 900), (0, 420, 120), lens=38), os.path.join(rd, "hero.png"), 1600, 1000, hide=cone)
    render(view_cam("v_station", (520, 820, 380), (0, 180, 90), lens=35), os.path.join(rd, "station.png"), 1600, 1000, hide=cone)
    render(view_cam("v_side", (2600, 420, 120), (0, 420, 120), ortho=1900), os.path.join(rd, "side_fov.png"), 1600, 1000)
    render(cam, os.path.join(rd, "camera_pov.png"), IMG_W, IMG_H, hide=cone)

    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "squint_rig.blend"))
    print("[rig] all must-see points in view:", ok)


main()
