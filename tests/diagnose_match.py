"""Diagnose matching quality on a real .blend file.

Run:
    blender.exe --background <file.blend> --python tests/diagnose_match.py -- <source> <target>
"""

import os
import sys

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from weight_match_tools import matching
from weight_match_tools.similarity import (cosine_similarity_matrix,
                                          subsample_indices)

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
src_name = argv[0] if argv else "2"
tgt_name = argv[1] if len(argv) > 1 else "1"

src = bpy.data.objects.get(src_name)
tgt = bpy.data.objects.get(tgt_name)
if src is None or tgt is None:
    meshes = sorted(
        (o for o in bpy.data.objects if o.type == 'MESH'),
        key=lambda o: len(o.vertex_groups), reverse=True)
    print("objects by vertex-group count:")
    for o in meshes[:10]:
        print(f"  {o.name!r}: {len(o.vertex_groups)} groups, "
              f"{len(o.data.vertices)} verts")
    raise SystemExit(1)

src_names = [vg.name for vg in src.vertex_groups]
tgt_names = [vg.name for vg in tgt.vertex_groups]
print(f"source {src.name!r}: {len(src_names)} groups, {len(src.data.vertices)} verts")
print(f"target {tgt.name!r}: {len(tgt_names)} groups, {len(tgt.data.vertices)} verts")

# local bounding boxes (the add-on compares in local space)
def bbox(obj):
    import numpy as np
    n = len(obj.data.vertices)
    arr = __import__("numpy").empty(n * 3)
    obj.data.vertices.foreach_get("co", arr)
    pts = arr.reshape(n, 3)
    return pts.min(axis=0), pts.max(axis=0)

smin, smax = bbox(src)
tmin, tmax = bbox(tgt)
print("src local bbox min", [round(x, 2) for x in smin], "max", [round(x, 2) for x in smax])
print("tgt local bbox min", [round(x, 2) for x in tmin], "max", [round(x, 2) for x in tmax])

# how much weight does each side actually carry?
def group_stats(obj, names):
    idx_col = {vg.index: i for i, vg in enumerate(obj.vertex_groups)
               if vg.name in set(names)}
    nonempty = [0] * len(names)
    total = [0.0] * len(names)
    for v in obj.data.vertices:
        for g in v.groups:
            col = idx_col.get(g.group)
            if col is not None and g.weight > 1e-4:
                nonempty[col] += 1
                total[col] += g.weight
    return nonempty, total

sn_verts, sn_sum = group_stats(src, src_names)
tn_verts, tn_sum = group_stats(tgt, tgt_names)
src_empty = [n for i, n in enumerate(src_names) if sn_verts[i] == 0]
tgt_empty = [n for i, n in enumerate(tgt_names) if tn_verts[i] == 0]
print(f"source groups with NO weighted verts: {len(src_empty)}"
      + (f" e.g. {src_empty[:8]}" if src_empty else ""))
print(f"target groups with NO weighted verts: {len(tgt_empty)}"
      + (f" e.g. {tgt_empty[:8]}" if tgt_empty else ""))

# weight-field similarity as the add-on computes it
vert_ids = subsample_indices(list(range(len(tgt.data.vertices))), 20000)
field = matching.sample_source_field(src, tgt, vert_ids, src_names)
tm = matching.weight_matrix(tgt, tgt_names, vert_ids)
sim = cosine_similarity_matrix(field, tm)

import numpy as np
best = sim.max(axis=1)
best_i = sim.argmax(axis=1)
order = np.argsort(best)[::-1]
print("\nbest-similarity distribution over source groups:")
buckets = [(1.0, 0.81), (0.8, 0.61), (0.6, 0.41), (0.41, 0.35), (0.35, 0.15), (0.15, -1.0)]
labels = ["0.81-1.0", "0.61-0.8", "0.41-0.6", "0.35-0.4", "0.15-0.35", "<0.15"]
for (hi, lo), lab in zip(buckets, labels):
    n = int(((best <= hi + 1e-9) & (best > lo)).sum())
    print(f"  {lab}: {n}")

print("\ntop 12 candidates:")
for i in order[:12]:
    print(f"  {src_names[i]!r} -> {tgt_names[best_i[i]]!r}  sim={best[i]:.3f}  "
          f"(src verts w/ weight: {sn_verts[i]})")
print("\njust below the 0.35 threshold (rank 70..90):")
for i in order[70:90]:
    print(f"  {src_names[i]!r} -> {tgt_names[best_i[i]]!r}  sim={best[i]:.3f}  "
          f"(src verts w/ weight: {sn_verts[i]})")
print(f"\nmatched at threshold 0.35: {(best >= 0.35).sum()}/{len(src_names)}")
print(f"matched at threshold 0.15: {(best >= 0.15).sum()}/{len(src_names)}")
print(f"matched at threshold 0.05: {(best >= 0.05).sum()}/{len(src_names)}")
