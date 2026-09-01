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
        # Keep the working copies at float32.  At the default 20k samples this
        # halves the peak normalization memory compared with float64, while a
        # float64 reduction keeps column norms accurate.
        out = np.array(m, dtype=np.float32, copy=True)
        norms = np.sqrt(np.sum(out * out, axis=0, dtype=np.float64))
        np.divide(out, norms[None, :] + 1e-9, out=out)
        return out

    s = _norm_cols(source_field)
    t = _norm_cols(target_field)
    result = (s.T @ t).astype(np.float32)
    np.clip(result, 0.0, 1.0, out=result)
    result[np.isclose(result, 0.0, atol=1e-7)] = 0.0
    result[np.isclose(result, 1.0, atol=1e-6)] = 1.0
    return result


def _minimum_cost_assignment(cost):
    """Rectangular Hungarian assignment for a matrix with rows <= columns."""
    cost = np.asarray(cost, dtype=np.float64)
    n_rows, n_cols = cost.shape
    if n_rows > n_cols:
        raise ValueError("assignment requires rows <= columns")

    # Potentials and predecessor arrays use the standard one-based Hungarian
    # representation; NumPy handles the per-column relaxation in bulk.
    u = np.zeros(n_rows + 1, dtype=np.float64)
    v = np.zeros(n_cols + 1, dtype=np.float64)
    p = np.zeros(n_cols + 1, dtype=np.int32)
    way = np.zeros(n_cols + 1, dtype=np.int32)

    for row in range(1, n_rows + 1):
        p[0] = row
        minv = np.full(n_cols + 1, np.inf, dtype=np.float64)
        used = np.zeros(n_cols + 1, dtype=bool)
        col0 = 0
        while True:
            used[col0] = True
            row0 = p[col0]
            cur = cost[row0 - 1] - u[row0] - v[1:]
            free_mask = ~used[1:]
            better = free_mask & (cur < minv[1:])
            minv_view = minv[1:]
            way_view = way[1:]
            minv_view[better] = cur[better]
            way_view[better] = col0

            free_cols = np.flatnonzero(free_mask) + 1
            col1 = int(free_cols[np.argmin(minv[free_cols])])
            delta = minv[col1]
            used_cols = np.flatnonzero(used)
            u[p[used_cols]] += delta
            v[used_cols] -= delta
            minv[~used] -= delta
            col0 = col1
            if p[col0] == 0:
                break

        while True:
            col1 = way[col0]
            p[col0] = p[col1]
            col0 = col1
            if col0 == 0:
                break

    assignment = np.full(n_rows, -1, dtype=np.int32)
    for col in range(1, n_cols + 1):
        if p[col]:
            assignment[p[col] - 1] = col - 1
    return assignment


def optimal_assignment(similarity, threshold, allow_merge=False):
    """Assign source columns to targets using the best valid global mapping.

    One-to-one mode maximizes total confidence while allowing a source to stay
    unmatched.  This avoids both the classic greedy failure and the opposite
    failure of sacrificing one near-certain pair merely to keep several
    threshold-level pairs.  Many-to-one mode is independent per source and
    therefore simply takes each source's best target.
    """
    sim = np.asarray(similarity, dtype=np.float32)
    if sim.ndim != 2:
        raise ValueError("similarity must be a 2D matrix")
    n_src, n_tgt = sim.shape
    src_ids = list(range(n_src))
    tgt_ids = list(range(n_tgt))
    if not src_ids or not tgt_ids:
        return {}

    clean = np.nan_to_num(sim, nan=-1.0, posinf=1.0, neginf=-1.0)
    if allow_merge:
        result = {}
        available = clean[np.ix_(src_ids, tgt_ids)]
        best_cols = np.argmax(available, axis=1)
        for row, best_col in enumerate(best_cols):
            value = float(available[row, best_col])
            if value >= threshold:
                result[src_ids[row]] = (tgt_ids[int(best_col)], value)
        return result

    scores = clean[np.ix_(src_ids, tgt_ids)]
    n_rows, n_real_cols = scores.shape
    # Dummy columns represent "leave unmatched" with zero benefit.  Invalid
    # real pairs are negative, so the optimizer only uses them during the
    # separate force-fill pass.
    benefits = np.zeros((n_rows, n_real_cols + n_rows), dtype=np.float64)
    valid = scores >= threshold
    benefits[:, :n_real_cols] = np.where(valid, scores, -1.0)
    chosen = _minimum_cost_assignment(-benefits)

    result = {}
    for row, col in enumerate(chosen):
        if col < n_real_cols and valid[row, col]:
            result[src_ids[row]] = (
                tgt_ids[int(col)], float(scores[row, col]))
    return result


def greedy_assignment(similarity, threshold, allow_merge=False):
    """Greedy assignment on a similarity matrix.

    Walks all (src, tgt) pairs by descending similarity and accepts a pair
    when both sides are still free.  With ``allow_merge``, several source
    groups may share a target group.

    Returns ``{src_index: (tgt_index, similarity)}``.
    """
    sim = np.asarray(similarity)
    n_src = sim.shape[0]

    pairs = []
    for s in range(n_src):
        for t in np.argsort(sim[s])[::-1]:
            value = float(sim[s, t])
            if value < threshold:
                break
            pairs.append((value, s, int(t)))
    pairs.sort(key=lambda p: (-p[0], p[1], p[2]))

    taken_greedy = set()
    assignment = {}
    for value, s, t in pairs:
        if s in assignment:
            continue
        if t in taken_greedy and not allow_merge:
            continue
        assignment[s] = (t, value)
        taken_greedy.add(t)
    return assignment


def complete_assignment(similarity, assignment, allow_merge=False):
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
    if not n_tgt:
        return assignment
    used_t = {t for t, _ in assignment.values()}

    remaining = [s for s in range(n_src) if s not in assignment]
    row_max = sim.max(axis=1)
    weighted = [s for s in remaining if row_max[s] > 0.0]
    empties = [s for s in remaining if row_max[s] <= 0.0]

    fallback_tgt = list(range(n_tgt))

    if allow_merge:
        def place(s):
            t = max(fallback_tgt, key=lambda t: (float(sim[s, t]), -t))
            return float(sim[s, t]), t
    else:
        def place(s):
            free = [t for t in range(n_tgt) if t not in used_t]
            pool = free if free else fallback_tgt
            return max((float(sim[s, t]), t) for t in pool)

    for s in sorted(weighted, key=lambda s: (row_max[s], -s), reverse=True):
        value, t = place(s)
        assignment[s] = (t, value)
        used_t.add(t)

    for s in empties:
        free = [t for t in range(n_tgt) if t not in used_t]
        t = free[-1] if free else fallback_tgt[0]
        assignment[s] = (t, 0.0)
        used_t.add(t)
    return assignment


def subsample_indices(indices, limit):
    """Evenly thin a list of vertex indices down to at most ``limit`` entries."""
    indices = list(indices)
    if limit <= 0 or len(indices) <= limit:
        return indices
    if limit == 1:
        return [indices[0]]
    last = len(indices) - 1
    return [indices[(i * last) // (limit - 1)] for i in range(limit)]
