"""shaded.py — Blender Workbench render of one GLB for a named view. Called by render.py:

    blender -b --factory-startup -P shaded.py -- <in.glb> <out.png> <iso|rear-iso|front|rear|side|plan>

Orthographic camera, flat studio lighting, outline + cavity shading — a clean "assembly instruction" look, seconds per frame.
"""
import math, sys
import bpy
from mathutils import Vector

glb, out, view = sys.argv[sys.argv.index("--") + 1:][:3]

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
if not objs:
    sys.exit("no meshes in glb")

# bounds in world space
pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
centre, size = (lo + hi) / 2, (hi - lo).length

DIRS = {  # camera direction from centre, up
    "iso": (Vector((1, -1.3, 0.8)), (0, 0, 1)), "rear-iso": (Vector((-1, 1.3, 0.8)), (0, 0, 1)),
    "front": (Vector((0, -1, 0)), (0, 0, 1)), "rear": (Vector((0, 1, 0)), (0, 0, 1)),
    "side": (Vector((1, 0, 0)), (0, 0, 1)), "plan": (Vector((0, 0, 1)), (0, 1, 0)),
}
d, up = DIRS.get(view, DIRS["iso"])
cam_data = bpy.data.cameras.new("cam"); cam_data.type = "ORTHO"; cam_data.ortho_scale = size * 1.35
cam_data.clip_end = size * 10
cam = bpy.data.objects.new("cam", cam_data); bpy.context.scene.collection.objects.link(cam)
cam.location = centre + d.normalized() * size * 3
direction = centre - cam.location
cam.rotation_euler = direction.to_track_quat("-Z", "Y" if view != "plan" else "Y").to_euler()
if view == "plan":
    cam.rotation_euler = (0, 0, 0); cam.location = centre + Vector((0, 0, size * 3))
bpy.context.scene.camera = cam

scene = bpy.context.scene
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "SINGLE"
scene.display.shading.single_color = (0.90, 0.84, 0.70)
scene.display.shading.show_cavity = True
scene.display.shading.show_object_outline = True
scene.display.shading.show_shadows = False
scene.display.shading.background_type = "VIEWPORT"
scene.display.shading.background_color = (1, 1, 1)
scene.render.film_transparent = False
scene.view_settings.view_transform = "Standard"
scene.world = bpy.data.worlds.new("w"); scene.world.color = (1, 1, 1)
scene.render.resolution_x, scene.render.resolution_y = 1600, 1100
scene.render.filepath = out
scene.render.image_settings.file_format = "PNG"
bpy.ops.render.render(write_still=True)
