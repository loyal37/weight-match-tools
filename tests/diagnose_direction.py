"""Compare target->source and source->target weight-field matching."""

import os
import sys

import bpy
import numpy as np
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from weight_match_tools import matching
from weight_match_tools import operators
from weight_match_tools.similarity import cosine_similarity_matrix, subsample_indices

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
src = bpy.data.objects[argv[0]]
tgt = bpy.data.objects[argv[1]]
src_names = [vg.name for vg in src.vertex_groups]

armature = next((m.object for m in tgt.modifiers
                 if m.type == 'ARMATURE' and m.object), None)
if armature:
    tgt_names = [vg.name for vg in tgt.vertex_groups
                 if armature.data.bones.get(vg.name)]
else:
    tgt_names = [vg.name for vg in tgt.vertex_groups]

limit = 20000

# Old direction: every target-body point looks for the nearest source garment.
tgt_ids = subsample_indices(range(len(tgt.data.vertices)), limit)
old_src = matching.sample_source_field(src, tgt, tgt_ids, src_names)
old_tgt = matching.weight_matrix(tgt, tgt_names, tgt_ids)
old_sim = cosine_similarity_matrix(old_src, old_tgt)

# New direction: compare only at vertices that actually belong to the garment.
src_ids = subsample_indices(range(len(src.data.vertices)), limit)
new_src = matching.weight_matrix(src, src_names, src_ids)
new_tgt = matching.sample_source_field(tgt, src, src_ids, tgt_names)
new_sim = cosine_similarity_matrix(new_src, new_tgt)

print(f"COMPARE source={src.name} target={tgt.name} "
      f"src_groups={len(src_names)} target_deform_groups={len(tgt_names)}")
for label, sim in (("OLD", old_sim), ("NEW", new_sim)):
    best = sim.max(axis=1)
    print(label, "BUCKETS",
          "high", int((best >= .8).sum()),
          "good", int(((best >= .6) & (best < .8)).sum()),
          "usable", int(((best >= .35) & (best < .6)).sum()),
          "low", int((best < .35).sum()))

interesting = [
    "Head", "Neck", "Left_shoulder", "Right_shoulder",
    "Left_elbow", "Right_elbow", "Sleeve_L", "Sleeve_R",
    "Left_knee", "Right_knee", "Spine",
]
for name in interesting:
    if name not in src_names:
        continue
    si = src_names.index(name)
    print("GROUP", name)
    for label, sim in (("OLD", old_sim), ("NEW", new_sim)):
        order = np.argsort(sim[si])[::-1][:5]
        print(" ", label, [(tgt_names[t], round(float(sim[si, t]), 3))
                           for t in order])

settings = SimpleNamespace(
    match_mode='WEIGHT', min_weight=.01, use_selected_only=False,
    sample_limit=20000, similarity_threshold=.35,
    allow_merge=True, force_match_all=True,
)
matched_src, matched_tgt, assignment, forced = operators._compute_assignment(
    src, tgt, settings)
mapping = {(name, side): (matched_tgt[assignment[i][0]], assignment[i][1])
           for i, (name, side) in enumerate(matched_src) if i in assignment}
print("FINAL_COUNTS", len(matched_src), len(matched_tgt), len(mapping), forced)
for name in interesting:
    for (source_name, side), (target_name, score) in mapping.items():
        if source_name == name:
            print("FINAL_MAP", name, side, "->", target_name,
                  round(float(score), 3))

# Apply in memory only; Blender exits without saving the source .blend.
pairs = [(name, side, mapping[(name, side)][0])
         for name, side in matched_src if (name, side) in mapping]
unmatched = operators._unmatched_nonempty_groups(src, tgt, pairs)
print("FINAL_UNMATCHED", len(unmatched), unmatched[:5])
operators._apply_mapping(src, tgt, pairs)
source_after = [vg.name for vg in src.vertex_groups]
target_template = [vg.name for vg in tgt.vertex_groups]
print("FINAL_EXACT", source_after == target_template,
      len(source_after), len(target_template))
