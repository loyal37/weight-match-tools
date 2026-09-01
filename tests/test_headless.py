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
check([vg.name for vg in src.vertex_groups] ==
      [vg.name for vg in tgt.vertex_groups],
      "apply_rename: source group ORDER matches the target")

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

# Normalized-name collisions must not silently become many-to-one unless the
# corresponding option is enabled.  The exact pair gets priority.
nsrc.vertex_groups.new(name="a_1")
ntgt.vertex_groups.new(name="A.1")
bpy.ops.weight_match.auto_match()
mapping = {k: v[0] for k, v in mapping_of(s).items()}
check(mapping.get("a_1") == "a_1" and mapping.get("A-1") == "A.1",
      f"NAME collision stays one-to-one and prefers the exact pair (got {mapping})")

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

print("=== Scenario E: force match all -> source ends up with target's names ===")
clear_scene()
fsrc = new_sphere("src_force", (0.0, 0.0, 0.0), 16)
paint(fsrc, "a", lambda co: clamp(co.z))       # will match 'x'
paint(fsrc, "b", lambda co: clamp(-co.z))      # will match 'y'
fsrc.vertex_groups.new(name="e1")              # empty -> excluded from matching
fsrc.vertex_groups.new(name="e2")

ftgt = new_sphere("tgt_force", (4.0, 0.0, 0.0), 16)
paint(ftgt, "x", lambda co: clamp(co.z))
paint(ftgt, "y", lambda co: clamp(-co.z))
ftgt.vertex_groups.new(name="z")

s = bpy.context.scene.weight_match
s.source_object = fsrc
s.target_object = ftgt
s.match_mode = 'WEIGHT'
s.similarity_threshold = 0.6
s.force_match_all = True
bpy.ops.weight_match.auto_match()

mapping = {k: v[0] for k, v in mapping_of(s).items()}
check(len(s.items) == 2 and set(mapping) == {"a", "b"},
      f"force: only weighted source groups participate (got {mapping})")
check(mapping.get("a") == "x" and mapping.get("b") == "y",
      f"force: strong pairs untouched (got {mapping})")
a_count = sum(1 for v in fsrc.data.vertices
              for g in v.groups if g.group == fsrc.vertex_groups["a"].index)
bpy.ops.weight_match.apply_rename()
names = {vg.name for vg in fsrc.vertex_groups}
check(names == {"x", "y", "z"},
      f"force+apply: source groups == target's set (got {sorted(names)})")
check([vg.name for vg in fsrc.vertex_groups] == ["x", "y", "z"],
      f"force+apply: count, names and order match target (got "
      f"{[vg.name for vg in fsrc.vertex_groups]})")
xvg = fsrc.vertex_groups["x"]
x_count = sum(1 for v in fsrc.data.vertices
              for g in v.groups if g.group == xvg.index)
check(x_count == a_count, f"force+apply: 'x' kept 'a' weights ({x_count} == {a_count})")

print("=== Scenario F: force + merge -> weak source joins its true region ===")
clear_scene()
wsrc = new_sphere("src_weak", (0.0, 0.0, 0.0), 24)
paint(wsrc, "p", lambda co: clamp(co.z))                  # strong: matches 'top'
paint(wsrc, "w", lambda co: 0.5 * clamp(co.z - 0.7))      # weak top-cap blob
wsrc.vertex_groups.new(name="e1")                          # empty
wsrc.vertex_groups.new(name="e2")                          # empty

wtgt = new_sphere("tgt_weak", (4.0, 0.0, 0.0), 24)
paint(wtgt, "top", lambda co: clamp(co.z))
paint(wtgt, "mid", lambda co: clamp(1.0 - abs(co.z) * 2))
paint(wtgt, "foot", lambda co: clamp(-co.z))

s = bpy.context.scene.weight_match
s.source_object = wsrc
s.target_object = wtgt
s.match_mode = 'WEIGHT'
s.similarity_threshold = 0.995   # push the weak blob into the force-fill pass
s.force_match_all = True
s.allow_merge = True
bpy.ops.weight_match.auto_match()
mapping = {k: v[0] for k, v in mapping_of(s).items()}
check(mapping.get("p") == "top", f"strong pair kept (got {mapping})")
check(mapping.get("w") == "top",
      f"weak top blob merges into already-taken 'top', not a free wrong one "
      f"(got {mapping})")
check(set(mapping) == {"p", "w"},
      f"empty source groups do not enter force-fill (got {mapping})")
s.similarity_threshold = 0.6

print("=== Scenario G: many-to-one transfer sums weights ===")
clear_scene()
msrc = new_sphere("src_m21", (0.0, 0.0, 0.0), 24)
paint(msrc, "a", lambda co: clamp(co.z))
paint(msrc, "b", lambda co: 0.5 * clamp(co.z))   # same region, half intensity
mtgt = new_sphere("tgt_m21", (4.0, 0.0, 0.0), 24)
paint(mtgt, "top", lambda co: clamp(co.z))

s = bpy.context.scene.weight_match
s.source_object = msrc
s.target_object = mtgt
s.match_mode = 'WEIGHT'
s.similarity_threshold = 0.6
s.allow_merge = True
bpy.ops.weight_match.auto_match()
mapping = {k: v[0] for k, v in mapping_of(s).items()}
check(mapping.get("a") == "top" and mapping.get("b") == "top",
      f"many-to-one: both sources map to 'top' (got {mapping})")

bpy.ops.weight_match.transfer_weights()
top_vg = mtgt.vertex_groups["top"]
half = min(mtgt.data.vertices, key=lambda v: abs(v.co.z - 0.5))
got = 0.0
for g in half.groups:
    if g.group == top_vg.index:
        got = g.weight
expected = 0.5 + 0.25  # a + b at z=0.5
check(abs(got - expected) < 0.05,
      f"many-to-one transfer sums weights at z=0.5: {got:.3f} ~ {expected}")

print("=== Scenario H: add-on language switch ===")
from weight_match_tools import i18n

s = bpy.context.scene.weight_match
lang_src = new_sphere("src_lang", (0.0, 0.0, 0.0), 8)
s.source_object = lang_src  # keep some state across the switch
s.items.clear()
row = s.items.add()
row.source_name = "p"
row.source_side = "POS"
row.target_name = "top"
row.similarity = 0.9


def source_object_label():
    rna = bpy.types.Scene.bl_rna.properties["weight_match"]
    return rna.fixed_type.bl_rna.properties["source_object"].name


check(source_object_label() == "源物体",
      f"default language is Chinese (got {source_object_label()!r})")
check(bpy.context.window_manager.wmt_lang.language == 'zh_CN',
      "language property defaults to zh_CN")

# Exercise the real property-update/deferred-callback path used by the UI.
bpy.context.window_manager.wmt_lang.language = 'en_US'
if bpy.app.timers.is_registered(i18n._apply_deferred):
    bpy.app.timers.unregister(i18n._apply_deferred)
i18n._apply_deferred()
check(source_object_label() == "Source",
      f"switch to English (got {source_object_label()!r})")
s2 = bpy.context.scene.weight_match
check(s2.source_object.name == "src_lang" and len(s2.items) == 1
      and s2.items[0].target_name == "top"
      and s2.items[0].source_side == "POS",
      "settings and mapping rows survive the language switch")
check(hasattr(bpy.types, "WEIGHTMATCH_PT_main")
      and bpy.types.WEIGHTMATCH_PT_main.bl_category == "Weight Match"
      and bpy.types.WEIGHTMATCH_PT_main.bl_label == "Weight Match",
      "add-on panel identity remains English after switching language")

bpy.context.window_manager.wmt_lang.language = 'zh_CN'
if bpy.app.timers.is_registered(i18n._apply_deferred):
    bpy.app.timers.unregister(i18n._apply_deferred)
i18n._apply_deferred()
check(source_object_label() == "源物体", "switch back to Chinese")
s3 = bpy.context.scene.weight_match
check(len(s3.items) == 1 and s3.items[0].source_name == "p",
      "mapping rows survive switching back")

print("=== Scenario I: batch match many sources -> one target ===")
clear_scene()


def new_cube(name, location):
    bpy.ops.mesh.primitive_cube_add(size=2, location=location)
    obj = bpy.context.active_object
    obj.name = name
    return obj


def paint_box(obj, name, axis, sign):
    vg = obj.vertex_groups.new(name=name)
    for v in obj.data.vertices:
        if sign * getattr(v.co, axis) > 0.0:
            vg.add([v.index], 1.0, 'REPLACE')


tobj = new_cube("tgt_bat", (10.0, 0.0, 0.0))
paint_box(tobj, "x", "x", -1)
paint_box(tobj, "y", "z", 1)

b1 = new_cube("bat_1", (0.0, 0.0, 0.0))
paint_box(b1, "a", "x", -1)
paint_box(b1, "b", "z", 1)
a_count = sum(1 for v in b1.data.vertices
              for g in v.groups if g.group == b1.vertex_groups["a"].index)

b2 = new_cube("bat_2", (5.0, 0.0, 0.0))
paint_box(b2, "c", "x", -1)
paint_box(b2, "d", "z", 1)
b2.vertex_groups.new(name="e")  # empty -> force-filled

s = bpy.context.scene.weight_match
s.target_object = tobj
s.match_mode = 'WEIGHT'
s.similarity_threshold = 0.6
s.force_match_all = True
s.allow_merge = True

b1.select_set(True)
b2.select_set(True)
tobj.select_set(True)  # must be skipped even though selected
bpy.ops.weight_match.batch_match()

for obj in (b1, b2):
    names = [vg.name for vg in obj.vertex_groups]
    check(names == ["x", "y"], f"batch: {obj.name} groups == target order (got {names})")
xvg = b1.vertex_groups["x"]
x_count = sum(1 for v in b1.data.vertices
              for g in v.groups if g.group == xvg.index)
check(x_count == a_count, f"batch: b1 'x' kept 'a' weights ({x_count} == {a_count})")
check(s.source_object.name == "bat_2",
      "batch: mapping table left on the last processed source")

print("=== Scenario J: large Unicode target enum remains stable ===")
clear_scene()
bpy.ops.mesh.primitive_plane_add(size=1)
usrc = bpy.context.active_object
paint(usrc, "来源组", lambda _co: 1.0)
bpy.ops.mesh.primitive_plane_add(size=1, location=(3.0, 0.0, 0.0))
utgt = bpy.context.active_object
for i in range(450):
    utgt.vertex_groups.new(name=f"辅助骨骼_{i}")
paint(utgt, "上半身3", lambda _co: 1.0)

s = bpy.context.scene.weight_match
s.source_object = usrc
s.target_object = utgt
s.match_mode = 'WEIGHT'
s.similarity_threshold = 0.5

from weight_match_tools import properties
enum_a = properties._target_group_items(None, bpy.context)
enum_b = properties._target_group_items(None, bpy.context)
check(enum_a is enum_b and len(enum_a) == 452,
      "dynamic enum reuses a persistent list for 451 Unicode group names")
entry = next(item for item in enum_a if item[0] == "上半身3")
check(entry[0] is entry[1], "Unicode enum identifier and label are stable strings")
bpy.ops.weight_match.auto_match()
check(len(s.items) == 1 and s.items[0].target_name == "上半身3",
      f"automatic mapping can write Unicode target name (got {mapping_of(s)})")

print("=== Scenario K: same names are not locked across LODs ===")
clear_scene()
lsrc = new_cube("src_lod", (0.0, 0.0, 0.0))
paint_box(lsrc, "same", "x", -1)
paint_box(lsrc, "other", "z", 1)
ltgt = new_cube("tgt_lod", (5.0, 0.0, 0.0))
# Deliberately swap the weight regions while keeping the same two names.
paint_box(ltgt, "same", "z", 1)
paint_box(ltgt, "other", "x", -1)

s = bpy.context.scene.weight_match
s.source_object = lsrc
s.target_object = ltgt
s.match_mode = 'WEIGHT'
s.similarity_threshold = 0.8
bpy.ops.weight_match.auto_match()
mapping = {k: v[0] for k, v in mapping_of(s).items()}
check(mapping == {"same": "other", "other": "same"},
      f"same names follow weight evidence instead of being locked (got {mapping})")
check("prefer_same_name" not in s.bl_rna.properties,
      "same-name locking option is absent from settings")

print("=== Scenario L: soft left/right tie-breaking ===")
clear_scene()
side_src = new_cube("src_side", (0.0, 0.0, 0.0))
paint_box(side_src, "Right_elbow", "x", -1)
side_tgt = new_cube("tgt_side", (4.0, 0.0, 0.0))
paint(side_tgt, "ひじ補助.L", lambda _co: 1.0)
paint(side_tgt, "ひじ補助.R", lambda _co: 1.0)
s = bpy.context.scene.weight_match
s.source_object = side_src
s.target_object = side_tgt
s.match_mode = 'WEIGHT'
s.similarity_threshold = 0.5
s.allow_merge = True
s.force_match_all = False
bpy.ops.weight_match.auto_match()
mapping = {k: v[0] for k, v in mapping_of(s).items()}
check(mapping.get("Right_elbow") == "ひじ補助.R",
      f"symmetric field uses same-side name as a soft tiebreak (got {mapping})")

print("=== Scenario M: deform candidates, complete target template ===")
clear_scene()
meta_src = new_cube("src_meta", (0.0, 0.0, 0.0))
paint(meta_src, "Right_part", lambda _co: 1.0)
meta_tgt = new_cube("tgt_meta", (4.0, 0.0, 0.0))
paint(meta_tgt, "Bone.R", lambda _co: 1.0)
paint(meta_tgt, "mmd_vertex_order", lambda _co: 1.0)

arm_data = bpy.data.armatures.new("meta_arm_data")
arm_obj = bpy.data.objects.new("meta_arm", arm_data)
bpy.context.collection.objects.link(arm_obj)
bpy.context.view_layer.objects.active = arm_obj
arm_obj.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
bone = arm_data.edit_bones.new("Bone.R")
bone.head = (0.0, 0.0, 0.0)
bone.tail = (0.0, 0.0, 1.0)
bpy.ops.object.mode_set(mode='OBJECT')
modifier = meta_tgt.modifiers.new("Armature", 'ARMATURE')
modifier.object = arm_obj

s = bpy.context.scene.weight_match
s.source_object = meta_src
s.target_object = meta_tgt
s.match_mode = 'WEIGHT'
s.similarity_threshold = 0.5
s.allow_merge = False
s.force_match_all = True
bpy.ops.weight_match.auto_match()
mapping = {k: v[0] for k, v in mapping_of(s).items()}
check(mapping == {"Right_part": "Bone.R"},
      f"non-bone metadata is excluded from automatic candidates (got {mapping})")
bpy.ops.weight_match.apply_rename()
check([vg.name for vg in meta_src.vertex_groups] ==
      [vg.name for vg in meta_tgt.vertex_groups],
      "Apply still reproduces the complete target template including metadata")

print("=== Scenario N: bilateral mirrored group splits into two targets ===")
clear_scene()
split_src = new_cube("src_split", (0.0, 0.0, 0.0))
paint(split_src, "Right_sleeve", lambda _co: 1.0)
split_tgt = new_cube("tgt_split", (4.0, 0.0, 0.0))
paint_box(split_tgt, "Arm.L", "x", 1)
paint_box(split_tgt, "Arm.R", "x", -1)

s = bpy.context.scene.weight_match
s.source_object = split_src
s.target_object = split_tgt
s.match_mode = 'WEIGHT'
s.similarity_threshold = 0.5
s.allow_merge = False
s.force_match_all = True
bpy.ops.weight_match.auto_match()
split_rows = {(it.source_side, it.target_name) for it in s.items
              if it.source_name == "Right_sleeve"}
check(split_rows == {('POS', 'Arm.L'), ('NEG', 'Arm.R')},
      f"bilateral group becomes +X/-X mapping rows (got {split_rows})")
bpy.ops.weight_match.apply_rename()
check([vg.name for vg in split_src.vertex_groups] == ["Arm.L", "Arm.R"],
      "bilateral Apply still exactly follows target names/order")
left = split_src.vertex_groups["Arm.L"]
right = split_src.vertex_groups["Arm.R"]
left_members = {v.index for v in split_src.data.vertices for g in v.groups
                if g.group == left.index and g.weight > .9}
right_members = {v.index for v in split_src.data.vertices for g in v.groups
                 if g.group == right.index and g.weight > .9}
check(left_members and all(split_src.data.vertices[i].co.x > 0
                           for i in left_members),
      "+X half is isolated in Arm.L")
check(right_members and all(split_src.data.vertices[i].co.x < 0
                            for i in right_members),
      "-X half is isolated in Arm.R")

print("=== Scenario O: disable and re-enable after language switching ===")
weight_match_tools.unregister()
check(not hasattr(bpy.types, "WEIGHTMATCH_PT_main")
      and not hasattr(bpy.types.WindowManager, "wmt_lang"),
      "disable removes UI and language RNA classes cleanly")
weight_match_tools.register()
reenabled = {
    "panel": hasattr(bpy.types, "WEIGHTMATCH_PT_main"),
    "language": (hasattr(bpy.types.WindowManager, "wmt_lang")
                 and bpy.context.window_manager.wmt_lang is not None),
    "settings": hasattr(bpy.types.Scene, "weight_match"),
}
check(all(reenabled.values()),
      f"add-on can be enabled again after language switching (got {reenabled})")

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
