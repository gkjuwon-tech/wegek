"""The bpy program WEGEK runs inside Blender (headless) to realize an Experience.

Reads an exported Experience JSON and builds THREE acts laid out along -Y so a single
camera flies act1 -> act2 -> act3 across the full frame range (the scroll hand-off).
Per act: imports the Tripo GLBs at their composed placements, keyframes their motion,
rigs studio + rim lighting, sets an HDRI/gradient world and a reflective floor, then
path-traces the frames AND exports the exact world-space data (coords, camera path,
lights) to export.json — the ground truth that gets baked into the site.

Run:  <python-with-bpy> build_scene.py <experience.json> <out_dir> <frames_per_act>
"""
import json
import math
import sys

import bpy
import mathutils

EXP_PATH, OUT_DIR = sys.argv[-3], sys.argv[-2]
FPA = int(sys.argv[-1])
ACT_SPACING = 40.0  # acts sit far apart in world space; camera travels between them

exp = json.load(open(EXP_PATH))
scenes = exp.get("scenes", [])[:3]


def hx(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def lin(c):
    return tuple(v ** 2.2 for v in c)


bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
export = {"project": exp.get("project_name"), "acts": []}


def material(obj_meshes, preset, palette):
    for o in obj_meshes:
        for sl in o.material_slots:
            m = sl.material
            if not m or not m.use_nodes:
                continue
            b = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if not b:
                continue
            if preset == "chrome":
                b.inputs["Metallic"].default_value = 0.95
                b.inputs["Roughness"].default_value = 0.18
            elif preset == "glass":
                b.inputs["Metallic"].default_value = 0.0
                b.inputs["Roughness"].default_value = 0.05
                if "Transmission Weight" in b.inputs:
                    b.inputs["Transmission Weight"].default_value = 1.0
            elif preset == "emissive":
                if "Emission Color" in b.inputs:
                    b.inputs["Emission Color"].default_value = (*lin(hx(palette[1])), 1)
                    b.inputs["Emission Strength"].default_value = 4.0


def import_glb(path):
    before = set(sc.objects)
    try:
        bpy.ops.import_scene.gltf(filepath=path)
    except Exception:
        return [], None
    new = [o for o in sc.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    if not meshes:
        return [], None
    mn = mathutils.Vector((1e9,) * 3); mx = mathutils.Vector((-1e9,) * 3)
    for o in meshes:
        for c in o.bound_box:
            w = o.matrix_world @ mathutils.Vector(c)
            mn = mathutils.Vector(min(mn[i], w[i]) for i in range(3))
            mx = mathutils.Vector(max(mx[i], w[i]) for i in range(3))
    ctr = (mn + mx) / 2; size = max(mx - mn) or 1.0
    holder = bpy.data.objects.new("holder", None); sc.collection.objects.link(holder)
    for o in new:
        if o.parent is None:
            o.parent = holder
    return meshes, (holder, ctr, 2.0 / size)


def world_hdri(palette):
    world = bpy.data.worlds.new("W"); sc.world = world; world.use_nodes = True
    nt = world.node_tree
    hdri = exp.get("_hdri_file")
    bg = nt.nodes.get("Background")
    if hdri:
        env = nt.nodes.new("ShaderNodeTexEnvironment")
        try:
            env.image = bpy.data.images.load(hdri)
            nt.links.new(env.outputs[0], bg.inputs[0])
            bg.inputs[1].default_value = 0.6
            return
        except Exception:
            pass
    bg.inputs[0].default_value = (*lin(hx(palette[0])), 1)
    bg.inputs[1].default_value = 0.25


# reflective floor spanning all acts
bpy.ops.mesh.primitive_plane_add(size=400, location=(0, -ACT_SPACING, -1.6))
fl = bpy.context.active_object
fm = bpy.data.materials.new("floor"); fm.use_nodes = True
fb = fm.node_tree.nodes["Principled BSDF"]
fb.inputs["Metallic"].default_value = 0.85
fb.inputs["Roughness"].default_value = 0.22
fl.data.materials.append(fm)
world_hdri(scenes[0].get("palette", ["#06080d", "#00e5ff", "#a06bff", "#eef6ff"]) if scenes else ["#06080d"])

cam = bpy.data.cameras.new("cam"); camo = bpy.data.objects.new("cam", cam)
sc.collection.objects.link(camo); sc.camera = camo
tgt = bpy.data.objects.new("camtgt", None); sc.collection.objects.link(tgt)
ccon = camo.constraints.new("TRACK_TO"); ccon.target = tgt

total_frames = FPA * max(1, len(scenes))
sc.frame_start = 1; sc.frame_end = total_frames

for ai, scene in enumerate(scenes):
    oy = -ai * ACT_SPACING               # this act's world offset on Y
    f0 = ai * FPA + 1; f1 = (ai + 1) * FPA
    pal = scene.get("palette", ["#06080d", "#00e5ff", "#a06bff", "#eef6ff"])
    act_rec = {"id": scene.get("id"), "offset_y": oy, "frame_range": [f0, f1], "objects": [], "camera": [], "lights": []}

    for ob in scene.get("objects", []):
        path = ob.get("model_local")
        if not path:
            continue
        meshes, info = import_glb(path)
        if not info:
            continue
        holder, ctr, autoscale = info
        s = autoscale * ob.get("scale", 1.0)
        holder.scale = (s, s, s)
        pos = ob.get("position", [0, 0, 0])
        base = (pos[0] - ctr.x * s, pos[1] + oy - ctr.y * s, pos[2] - ctr.z * s)
        rot = ob.get("rotation", [0, 0, 0])
        material(meshes, ob.get("material", "chrome"), pal)
        # keyframe motion across this act's frame sub-range
        kfs = ob.get("keyframes") or [{"t": 0, "position": [0, 0, 0], "rotation": [0, 0, 0], "scale": 1}]
        for kf in kfs:
            fr = int(f0 + (f1 - f0) * kf.get("t", 0))
            kp = kf.get("position", [0, 0, 0]); kr = kf.get("rotation", [0, 0, 0]); ks = kf.get("scale", 1)
            holder.location = (base[0] + kp[0], base[1] + kp[1], base[2] + kp[2])
            holder.rotation_euler = (rot[0] + kr[0], rot[1] + kr[1], rot[2] + kr[2])
            holder.scale = (s * ks, s * ks, s * ks)
            holder.keyframe_insert("location", frame=fr)
            holder.keyframe_insert("rotation_euler", frame=fr)
            holder.keyframe_insert("scale", frame=fr)
        act_rec["objects"].append({"id": ob.get("id"), "base": list(base), "rotation": rot, "scale": s})

    for li in scene.get("lights", []):
        ld = bpy.data.lights.new(li.get("id", "L"), li.get("type", "area").upper() if li.get("type", "area") != "area" else "AREA")
        ld.energy = li.get("energy", 1000); ld.color = lin(hx(li.get("color", "#ffffff")))
        if ld.type == "AREA":
            ld.size = li.get("size", 5)
        lo = bpy.data.objects.new(li.get("id", "L"), ld)
        p = li.get("position", [4, -4, 5]); lo.location = (p[0], p[1] + oy, p[2])
        sc.collection.objects.link(lo)
        lc = lo.constraints.new("TRACK_TO"); lc.target = tgt
        act_rec["lights"].append({"type": ld.type, "position": list(lo.location), "energy": ld.energy, "is_rim": li.get("is_rim", False)})

    # camera flies through this act over its frame range, tracking the act centre
    cam_keys = scene.get("camera") or [{"t": 0, "position": [0, -8, 2.5], "fov": 42}]
    for ck in cam_keys:
        fr = int(f0 + (f1 - f0) * ck.get("t", 0))
        cp = ck.get("position", [0, -8, 2.5])
        camo.location = (cp[0], cp[1] + oy, cp[2])
        camo.data.angle = math.radians(ck.get("fov", 42))
        camo.keyframe_insert("location", frame=fr)
        camo.data.keyframe_insert("lens", frame=fr)
        act_rec["camera"].append({"frame": fr, "position": list(camo.location), "fov": ck.get("fov", 42)})
    # target sits at this act centre during the act
    tgt.location = (0, oy, 0); tgt.keyframe_insert("location", frame=(f0 + f1) // 2)
    export["acts"].append(act_rec)

# render settings — preview = SOLID/Workbench (sub-second, for the feedback loop);
# final = Cycles path tracing.
quality = exp.get("_quality", "final")
if quality == "preview":
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    sh.light = "STUDIO"; sh.color_type = "MATERIAL"; sh.show_shadows = True
    sc.render.resolution_x = int(exp.get("_w", 640)); sc.render.resolution_y = int(exp.get("_h", 360))
else:
    sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"
    sc.cycles.samples = int(exp.get("_samples", 24)); sc.cycles.use_denoising = True
    sc.render.resolution_x = int(exp.get("_w", 1280)); sc.render.resolution_y = int(exp.get("_h", 720))
sc.render.image_settings.file_format = "PNG"
sc.render.filepath = OUT_DIR.rstrip("/") + "/f_"
bpy.ops.render.render(animation=True)

with open(OUT_DIR.rstrip("/") + "/export.json", "w") as f:
    json.dump(export, f, indent=2)
print("WEGEK_BLENDER_DONE", total_frames, "frames")
