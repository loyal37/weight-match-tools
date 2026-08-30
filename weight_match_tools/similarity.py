"""Pure-math helpers shared by the matching pipeline.

Only depends on numpy so the logic can be unit-tested outside Blender.
"""

import numpy as np


def normalized_name(name):
    """Lowercase and keep only letters/digits, so 'DEF-Arm.01.L' and
    'def_arm_01_l' collapse to the same key."""
    return "".join(ch for ch in name.lower() if ch.isalnum())


def cosine_similarity_matrix(source_field, target_field):
    """Column-wise cosine similarity between two (N, G) weight matrices.

    ``source_field`` columns are source groups sampled onto the target
    surface; ``target_field`` columns are the target's own group weights over
    the same vertices.  Returns a (Gs, Gt) matrix in the 0..1 range because
    weights are non-negative.
    """

    def _norm_cols(m):
        norms = np.linalg.norm(m, axis=0, keepdims=True)
        return m / (norms + 1e-9)

    s = _norm_cols(np.asarray(source_field, dtype=np.float64))
    t = _norm_cols(np.asarray(target_field, dtype=np.float64))
    return (s.T @ t).astype(np.float32)


def greedy_assignment(similarity, threshold, allow_merge=False,
                      locked_src=(), locked_tgt=()):
    """Greedy assignment on a similarity matrix.

    Walks all (src, tgt) pairs by descending similarity and accepts a pair
    when both sides are still free.  ``locked_src`` / ``locked_tgt`` are
    column indices already assigned by an earlier rule (e.g. identical
    names); they stay exclusive even when ``allow_merge`` is on, which only
    lets several *unlocked* source groups share a target group.

    Returns ``{src_index: (tgt_index, similarity)}``.
    """
    sim = np.asarray(similarity)
    n_src = sim.shape[0]
    locked_src = set(locked_src)
    locked_tgt = set(locked_tgt)

    pairs = []
    for s in range(n_src):
        if s in locked_src:
            continue
        for t in np.argsort(sim[s])[::-1]:
            value = float(sim[s, t])
            if value < threshold:
                break
            pairs.append((value, s, int(t)))
    pairs.sort(key=lambda p: (-p[0], p[1], p[2]))

    used_t = set(locked_tgt)
    taken_greedy = set()
    assignment = {}
    for value, s, t in pairs:
        if s in assignment:
            continue
        if t in used_t:
            continue
        if t in taken_greedy and not allow_merge:
            continue
        assignment[s] = (t, value)
        taken_greedy.add(t)
    return assignment


def subsample_indices(indices, limit):
    """Evenly thin a list of vertex indices down to at most ``limit`` entries."""
    indices = list(indices)
    if limit <= 0 or len(indices) <= limit:
        return indices
    step = len(indices) / float(limit)
    return [indices[int(i * step)] for i in range(limit)]
