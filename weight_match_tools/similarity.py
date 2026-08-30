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


def complete_assignment(similarity, assignment, locked_tgt=(), allow_merge=False):
    """Fill ``assignment`` so every source column ends up with a target.

    Used for "Match All (Force)".  Sources with a real weight signal are
    placed first, best similarity first:

    * with ``allow_merge`` a source whose best target is already taken is
      merged into it anyway - e.g. a weakly weighted source breast bone joins
      the target bone that owns that region instead of grabbing an unrelated
      free one;
    * without ``allow_merge`` sources claim the best still-free target, so
      the mapping stays 1:1 as long as possible.

    All-zero sources (empty groups) go last: they spread over the remaining
    free targets and only share targets once none are left, so their forced
    renames never pollute real weights.
    """
    sim = np.asarray(similarity)
    n_src, n_tgt = sim.shape
    used_t = {t for t, _ in assignment.values()}
    used_t.update(locked_tgt)

    remaining = [s for s in range(n_src) if s not in assignment]
    row_max = sim.max(axis=1) if n_tgt else np.zeros(0)
    weighted = [s for s in remaining if row_max[s] > 0.0]
    empties = [s for s in remaining if row_max[s] <= 0.0]

    if allow_merge:
        def place(s):
            t = int(np.argmax(sim[s]))
            return float(sim[s, t]), t
    else:
        def place(s):
            free = [t for t in range(n_tgt) if t not in used_t]
            pool = free if free else range(n_tgt)
            return max((float(sim[s, t]), t) for t in pool)

    for s in sorted(weighted, key=lambda s: (row_max[s], -s), reverse=True):
        value, t = place(s)
        assignment[s] = (t, value)
        used_t.add(t)

    for s in empties:
        free = [t for t in range(n_tgt) if t not in used_t]
        t = free[-1] if free else int(np.argmax(sim[s]))
        assignment[s] = (t, 0.0)
        used_t.add(t)
    return assignment


def subsample_indices(indices, limit):
    """Evenly thin a list of vertex indices down to at most ``limit`` entries."""
    indices = list(indices)
    if limit <= 0 or len(indices) <= limit:
        return indices
    step = len(indices) / float(limit)
    return [indices[int(i * step)] for i in range(limit)]
