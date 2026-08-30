"""Unit tests for the numpy-only matching logic.

Run with the system Python (needs numpy):
    py tests/test_similarity.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "weight_match_tools"))

from similarity import (complete_assignment, cosine_similarity_matrix,
                        greedy_assignment, normalized_name, subsample_indices)

failures = []


def check(cond, msg):
    if cond:
        print(f"  ok  - {msg}")
    else:
        failures.append(msg)
        print(f"  FAIL - {msg}")


print("normalized_name")
check(normalized_name("DEF-Arm.01.L") == normalized_name("def_arm_01_l"),
      "'DEF-Arm.01.L' == 'def_arm_01_l' after cleanup")
check(normalized_name("  Spine_2 ") == "spine2", "whitespace/punctuation stripped")

print("cosine_similarity_matrix")
# 4 verts; source groups A,B,C,D; D duplicates A on purpose (conflict test)
src = np.array([[1.0, 0.0, 0.5, 1.0],
                [1.0, 0.0, 0.5, 1.0],
                [0.0, 1.0, 0.5, 0.0],
                [0.0, 1.0, 0.5, 0.0]])
tgt = np.array([[1.0, 0.0, 1.0],
                [1.0, 0.0, 1.0],
                [0.0, 1.0, 1.0],
                [0.0, 1.0, 1.0]])  # target groups X,Y,Z
sim = cosine_similarity_matrix(src, tgt)
check(sim.shape == (4, 3), "similarity matrix shape is (Gs, Gt)")
check(abs(sim[0, 0] - 1.0) < 1e-6, "identical fields A/X similarity == 1")
check(abs(sim[0, 1]) < 1e-6, "disjoint fields A/Y similarity == 0")
check(abs(sim[2, 2] - 1.0) < 1e-6, "uniform C matches all-ones Z exactly")
check(abs(sim[2, 0] - 2 / (2 * np.sqrt(2))) < 1e-6,
      "uniform C vs half field X = 0.7071")
check((sim >= 0.0).all() and (sim <= 1.0).all(), "similarities within 0..1")

print("greedy_assignment (1:1)")
a = greedy_assignment(sim, threshold=0.6)
check(a.get(0) == (0, 1.0), "A -> X at similarity 1.0")
check(a.get(1) == (1, 1.0), "B -> Y at similarity 1.0")
check(a.get(2) == (2, 1.0), "C -> Z at similarity 1.0")
check(3 not in a, "duplicate D blocked by 1:1 when X is taken")

print("greedy_assignment (many-to-one)")
a = greedy_assignment(sim, threshold=0.6, allow_merge=True)
check(a.get(0) == (0, 1.0), "A -> X")
check(a.get(1) == (1, 1.0), "B -> Y")
check(a.get(2) == (2, 1.0), "C -> Z")
check(a.get(3) == (0, 1.0), "duplicate D merges into X when merge allowed")

print("greedy_assignment (locks)")
a = greedy_assignment(sim, threshold=0.6, allow_merge=True,
                      locked_src={0}, locked_tgt={2})
check(0 not in a, "locked source column skipped")
check(a.get(1) == (1, 1.0), "B -> Y unchanged")
check(a.get(3) == (0, 1.0), "D takes X while A is locked away")
check(abs(a.get(2, (9, 0))[1] - 2 / (2 * np.sqrt(2))) < 1e-6,
      "C merges into the leftover X at 0.7071 when merge allowed")
a = greedy_assignment(sim, threshold=0.6, allow_merge=False,
                     locked_src={0}, locked_tgt={2})
check(2 not in a, "C left unmatched with merge off: its targets are taken")

print("greedy_assignment (threshold)")
a = greedy_assignment(sim, threshold=0.8)
check(set(a) == {0, 1, 2}, "only the 1.0 pairs survive a high threshold")

print("complete_assignment (force fill)")
# 6 source groups over 3 verts; A and D identical, C/E/F all-zero (empty)
groups = np.array([[1.0, 0.0, 0.5],   # A
                   [0.0, 1.0, 0.0],   # B
                   [0.0, 0.0, 0.0],   # C (empty)
                   [1.0, 0.0, 0.5],   # D == A
                   [0.0, 0.0, 0.0],   # E (empty)
                   [0.0, 0.0, 0.0]])  # F (empty)
verts2 = groups.T                      # (3 verts, 6 groups)
tgt2 = np.eye(3)                       # targets X, Y, Z
sim2 = cosine_similarity_matrix(verts2, tgt2)
partial = greedy_assignment(sim2, threshold=0.6)
full = complete_assignment(sim2, dict(partial))
check(len(full) == 6, "every source column ends up assigned")
check(full[0][0] == 0, "A -> X")
check(full[1][0] == 1, "B -> Y")
check(full[3][0] == 2, "duplicate D takes the still-free Z before empties")
check(all(t in (0, 1, 2) for _, (t, _) in full.items()), "targets stay in range")
check(all(v >= 0.0 for _, (_, v) in full.items()), "recorded similarities sane")

full_m = complete_assignment(sim2, dict(partial), allow_merge=True)
check(len(full_m) == 6, "merge mode: every source column assigned")
check(full_m[3][0] == 0 and full_m[3][1] > 0.85,
      "merge mode: duplicate D merges into its best target X even though Z is free")
check(full_m[2] == (2, 0.0), "merge mode: empty C spreads onto the free Z")
check(full_m[4][0] == 0 and full_m[5][0] == 0,
      "merge mode: leftover empties share a target harmlessly")

print("subsample_indices")
sub = subsample_indices(list(range(100)), 10)
check(len(sub) == 10, "thinned to limit")
check(sub[0] == 0 and sub[-1] == 90, "even stride covers the range")
check(subsample_indices(list(range(5)), 10) == [0, 1, 2, 3, 4],
      "shorter lists pass through")

print()
if failures:
    print(f"{len(failures)} FAILURE(S)")
    sys.exit(1)
print("ALL SIMILARITY TESTS PASSED")
