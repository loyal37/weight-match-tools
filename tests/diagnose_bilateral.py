"""Inspect side distribution and inverse arm mappings in a real Blender file."""

import os
import sys
from types import SimpleNamespace

import bpy
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from weight_match_tools import matching, operators


argv = sys.argv[sys.argv.index("--") + 1:]
src = bpy.data.objects[argv[0]]
tgt = bpy.data.objects[argv[1]]
settings = SimpleNamespace(
    match_mode='WEIGHT', min_weight=.01, use_selected_only=False,
    sample_limit=20000, similarity_threshold=.19,
    allow_merge=True, force_match_all=True,
)
print("SPLIT_CENTER", matching.split_center_x(src))
src_channels, tgt_names, assignment, _forced = operators._compute_assignment(
    src, tgt, settings)

arm_tokens = ("肩", "腕", "ひじ", "手", "上半身", "首", "頭")
for si, (ti, score) in assignment.items():
    target = tgt_names[ti]
    if any(token in target for token in arm_tokens):
        print("ARM_MAP", src_channels[si], "->", target,
              round(float(score), 3))

coords = matching.mesh_coords_np(src.data)
for name in matching.nonempty_group_names(
        src, [vg.name for vg in src.vertex_groups]):
    side = matching.name_side(name)
    if side is None:
        continue
    matrix = matching.weight_matrix(src, [name])[:, 0]
    total = float(matrix.sum())
    if total <= 1e-8:
        continue
    pos = float(matrix[coords[:, 0] > 1e-6].sum())
    neg = float(matrix[coords[:, 0] < -1e-6].sum())
    if min(pos, neg) / total >= .1:
        print("BILATERAL", name, "side", side,
              "pos", round(pos / total, 3), "neg", round(neg / total, 3))
