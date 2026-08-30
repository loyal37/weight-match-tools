"""Headless integration test against real Blender.

Run with:
    "D:/blender4,5/blender.exe" --background --factory-startup \
        --python tests/test_headless.py
"""

import os
import sys

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import weight_match_tools

failures = []


def check(cond, msg):
    print(("  ok  - " if cond else "  FAIL - ") + msg)
    if not cond:
        failures.append(msg)


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def new_sphere(name, location, segments):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments, ring_count=max(8, segments // 2), location=location)
    obj = bpy.context.active_object
    obj.name = name
    return obj


def clamp(x):
    return max(0.0, min(1.0, x))


def paint(obj, group_name, fn):
    vg = obj.vertex_groups.new(name=group_name)
    for v in obj.data.vertices:
        w = clamp(fn(v.co))
        if w > 1e-3:
            vg.add([v.index], w, 'REPLACE')


def mapping_of(settings):
    return {it.source_name: (it.target_name, it.similarity) for it in settings.items}


print("=== Scenario A: WEIGHT field matching + transfer + rename ===")
clear_scene()
weight_match_tools.register()

src = new_sphere("src_A", (0.0, 0.0, 0.0), 32)
paint(src, "3", lambda co: clamp(co.z))                # top
paint(src, "2", lambda co: clamp(1.0 - abs(co.z) * 2))  # middle band
paint(src, "1", lambda co: clamp(-co.z))                # bottom

tgt = new_sphere("tgt_A", (3.0, 0.0, 0.0), 24)  # different resolution & position
paint(tgt, "head", lambda co: clamp(co.z))
paint(tgt, "body", lambda co: clamp(1.0 - abs(co.z) * 2))
paint(tgt, "foot", lambda co: clamp(-co.z))
tgt.vertex_groups.new(name="tail")  # target-only group -> must be created empty on source

# empty clone that will actually receive the transferred weights
tgt_recv = new_sphere("tgt_recv", (6.0, 0.0, 0.0), 24)
for g in ("head", "body", "foot", "tail"):
    tgt_recv.vertex_groups.new(name=g)

s = bpy.context.scene.weight_match
s.source_object = src
s.target_object = tgt
s.match_mode = 'WEIGHT'
s.similarity_threshold = 0.6
bpy.ops.weight_match.auto_match()

mapping = mapping_of(s)
for sname, tname, min_sim in (("3", "head", 0.9), ("2", "body", 0.6), ("1", "foot", 0.9)):
    got_name, got_sim = mapping.get(sname, (None, 0.0))
    check(got_name == tname,
          f"match '{sname}' -> '{tname}' (got {got_name!r}, sim {got_sim:.3f})")
    check(got_sim > min_sim,
          f"similarity('{sname}') > {min_sim} (got {got_sim:.3f})")


def recv_weights(vg):
    out = {}
    for v in tgt_recv.data.vertices:
        for g in v.groups:
            if g.group == vg.index:
                out[v.index] = g.weight
    return out


# Transfer onto the empty clone (source still has its original names).
s.target_object = tgt_recv
bpy.ops.weight_match.transfer_weights()
head = recv_weights(tgt_recv.vertex_groups["head"])
check(len(head) > 0, "transfer: 'head' received weights")
check(max(head.values(), default=0.0) > 0.9,
      f"transfer: 'head' max weight > 0.9 (got {max(head.values(), default=0.0):.3f})")
top = max(tgt_recv.data.vertices, key=lambda v: v.co.z)
bottom = min(tgt_recv.data.vertices, key=lambda v: v.co.z)
check(head.get(top.index, 0.0) > 0.9, "transfer: top vertex ~1.0 in 'head'")
check(head.get(bottom.index, 0.0) < 0.1, "transfer: bottom vertex ~0.0 in 'head'")
foot = recv_weights(tgt_recv.vertex_groups["foot"])
check(foot.get(bottom.index, 0.0) > 0.9, "transfer: bottom vertex ~1.0 in 'foot'")
check(foot.get(top.index, 0.0) < 0.1, "transfer: top vertex ~0.0 in 'foot'")

# Apply to source: renames the source groups and fills the missing 'tail'.
s.target_object = tgt
bpy.ops.weight_match.apply_rename()
names = {vg.name for vg in src.vertex_groups}
check(names == {"head", "body", "foot", "tail"},
      f"apply_rename: source groups now {sorted(names)}")

# The same mapping still transfers after Apply (falls back to target names).
bpy.ops.weight_match.transfer_weights()
head2 = recv_weights(tgt_recv.vertex_groups["head"])
check(head2.get(top.index, 0.0) > 0.9,
      "transfer after apply_rename still works (name fallback)")

print("=== Scenario B: CENTROID matching ===")
clear_scene()
bpy.ops.mesh.primitive_cube_add(size=2, location=(0.0, 0.0, 0.0))
csrc = bpy.context.active_object
csrc.name = "src_cube"
bpy.ops.mesh.primitive_cube_add(size=2, location=(6.0, 0.0, 0.0))
ctgt = bpy.context.active_object
ctgt.name = "tgt_cube"


def paint_side(obj, name, axis, sign):
    vg = obj.vertex_groups.new(name=name)
    for v in obj.data.vertices:
        if sign * getattr(v.co, axis) > 0.0:
            vg.add([v.index], 1.0, 'REPLACE')


paint_side(csrc, "L", "x", -1)
paint_side(csrc, "R", "x", +1)
paint_side(csrc, "U", "z", +1)
paint_side(ctgt, "left", "x", -1)
paint_side(ctgt, "right", "x", +1)
paint_side(ctgt, "up", "z", +1)

s = bpy.context.scene.weight_match
s.source_object = csrc
s.target_object = ctgt
s.match_mode = 'CENTROID'
s.similarity_threshold = 0.5
bpy.ops.weight_match.auto_match()
mapping = {k: v[0] for k, v in mapping_of(s).items()}
check(mapping == {"L": "left", "R": "right", "U": "up"},
      f"CENTROID mapping (got {mapping})")

print("=== Scenario C: NAME matching ===")
clear_scene()
bpy.ops.mesh.primitive_plane_add(size=1, location=(0.0, 0.0, 0.0))
nsrc = bpy.context.active_object
nsrc.vertex_groups.new(name="A-1")
nsrc.vertex_groups.new(name="same")
bpy.ops.mesh.primitive_plane_add(size=1, location=(10.0, 0.0, 0.0))
ntgt = bpy.context.active_object
ntgt.vertex_groups.new(name="a_1")
ntgt.vertex_groups.new(name="same")

s = bpy.context.scene.weight_match
s.source_object = nsrc
s.target_object = ntgt
s.match_mode = 'NAME'
bpy.ops.weight_match.auto_match()
mapping = {k: v[0] for k, v in mapping_of(s).items()}
check(mapping == {"A-1": "a_1", "same": "same"},
      f"NAME mapping ignores punctuation/case (got {mapping})")

print("=== Scenario D: rename with merge into existing group ===")
clear_scene()
bpy.ops.mesh.primitive_cube_add(size=2, location=(0.0, 0.0, 0.0))
msrc = bpy.context.active_object
msrc.name = "src_merge"
vg_a = msrc.vertex_groups.new(name="A")
vg_b = msrc.vertex_groups.new(name="B")
for v in msrc.data.vertices:
    if v.co.z < 0.0:
        vg_a.add([v.index], 1.0, 'REPLACE')
    if v.co.x > 0.0:
        vg_b.add([v.index], 1.0, 'REPLACE')

bpy.ops.mesh.primitive_cube_add(size=2, location=(6.0, 0.0, 0.0))
mtgt = bpy.context.active_object
mtgt.vertex_groups.new(name="B")

s = bpy.context.scene.weight_match
s.source_object = msrc
s.target_object = mtgt
s.create_missing = False
s.items.clear()
row = s.items.add()
row.source_name = "A"
row.target_enum = "B"
row = s.items.add()
row.source_name = "B"
row.target_enum = "B"
bpy.ops.weight_match.apply_rename()

names = {vg.name for vg in msrc.vertex_groups}
check(names == {"B"}, f"merge: only 'B' remains (got {sorted(names)})")
bvg = msrc.vertex_groups["B"]
count = sum(1 for v in msrc.data.vertices
            for g in v.groups if g.group == bvg.index)
check(count == 6, f"merge: 6 vertices in merged 'B' (got {count})")

print()
result_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "last_headless_result.txt")
if failures:
    print(f"{len(failures)} HEADLESS TEST FAILURE(S)")
    with open(result_path, "w") as f:
        f.write("FAIL\n")
    sys.exit(1)
print("ALL HEADLESS TESTS PASSED")
with open(result_path, "w") as f:
    f.write("PASS\n")
