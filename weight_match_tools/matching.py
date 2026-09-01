"""Weight-field extraction, surface sampling and spatial matching.

Spatial comparisons happen in each object's LOCAL space, so they are
independent of where the meshes sit in the scene; they assume the two meshes
line up in their own modeling space (re-rigged variants of the same base
mesh), which is the typical rename/transfer workflow.
"""

import re

import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.interpolate import poly_3d_calc

from .similarity import normalized_name


def name_side(name):
    """Return ``'L'``/``'R'`` for explicit side markers, else ``None``."""
    if "左" in name:
        return 'L'
    if "右" in name:
        return 'R'
    tokens = [token for token in re.split(r"[^a-z0-9]+", name.casefold())
              if token]
    if "left" in tokens or "l" in tokens:
        return 'L'
    if "right" in tokens or "r" in tokens:
        return 'R'
    return None


def channel_parts(channel):
    """Return ``(group_name, spatial_half)`` for a source channel.

    Plain strings are ordinary whole vertex groups.  Auto matching may also
    use ``(name, 'POS')`` and ``(name, 'NEG')`` channels when one explicitly
    side-named source group actually contains weights on both halves of a
    symmetric mesh.
    """
    if isinstance(channel, (tuple, list)):
        return str(channel[0]), str(channel[1] or "")
    return str(channel), ""


def split_center_x(obj):
    """Local-X center of an object's bounding box."""
    coords = mesh_coords_np(obj.data)
    if not len(coords):
        return 0.0
    return float((coords[:, 0].min() + coords[:, 0].max()) * 0.5)


def source_group_channels(obj, group_names, minimum_side_share=0.35):
    """Expand truly bilateral side groups into positive/negative-X channels.

    Some imported garments collapse a mirrored pair into one vertex group
    (for example ``Right_elbow`` can contain exactly half of its weight on
    each sleeve).  Renaming that whole group to one target bone necessarily
    makes the other sleeve follow the wrong bone.  Such groups are represented
    as two virtual channels so matching and Apply can partition their weights.

    Central groups are never split.  A group needs an explicit L/R marker and
    at least ``minimum_side_share`` of its total weight on each spatial half.
    """
    group_names = list(group_names)
    if not group_names:
        return []
    coords = mesh_coords_np(obj.data)
    center = split_center_x(obj)
    index_to_col = {
        vg.index: i for i, name in enumerate(group_names)
        if (vg := obj.vertex_groups.get(name)) is not None
    }
    sums = np.zeros((len(group_names), 2), dtype=np.float64)
    for vertex in obj.data.vertices:
        half = 0 if coords[vertex.index, 0] >= center else 1
        for element in vertex.groups:
            col = index_to_col.get(element.group)
            if col is not None:
                sums[col, half] += element.weight

    channels = []
    for i, name in enumerate(group_names):
        pos, neg = sums[i]
        total = pos + neg
        bilateral = (name_side(name) is not None and total > 1e-8
                     and pos / total >= minimum_side_share
                     and neg / total >= minimum_side_share)
        if bilateral:
            channels.extend(((name, 'POS'), (name, 'NEG')))
        else:
            channels.append((name, ''))
    return channels


def apply_side_bias(similarity, src_names, tgt_names, strength=0.05):
    """Softly prefer matching explicit left/right names to the same side.

    This is deliberately not a lock: strong spatial/weight evidence can still
    override a naming convention, while near-symmetric ties stop crossing
    from one side of the character to the other.
    """
    out = np.array(similarity, dtype=np.float32, copy=True)
    # A split channel already carries reliable spatial evidence.  Do not let
    # its original (and often misleading) L/R name pull the +X half back to
    # the wrong target side.
    src_sides = [name_side(channel_parts(name)[0])
                 if not channel_parts(name)[1] else None
                 for name in src_names]
    tgt_sides = [name_side(name) for name in tgt_names]
    for s, src_side in enumerate(src_sides):
        if src_side is None:
            continue
        for t, tgt_side in enumerate(tgt_sides):
            if tgt_side is None:
                continue
            factor = 1.0 + strength if src_side == tgt_side else 1.0 - strength
            out[s, t] *= factor
    np.clip(out, 0.0, 1.0, out=out)
    return out


def mesh_coords_np(mesh):
    """(V, 3) array of vertex coordinates in object space."""
    count = len(mesh.vertices)
    arr = np.empty(count * 3, dtype=np.float64)
    if count:
        mesh.vertices.foreach_get("co", arr)
    return arr.reshape(count, 3)


def weight_matrix(obj, group_names, vert_indices=None):
    """(N, G) matrix of vertex-group weights.

    Rows follow ``vert_indices`` (or all vertices), columns follow
    ``group_names``.  Groups missing from the object simply stay zero
    columns.  Note: vertex groups live on the Object, not the Mesh.
    """
    verts = obj.data.vertices
    if vert_indices is None:
        vert_indices = range(len(verts))
    vert_indices = list(vert_indices)

    channels = [channel_parts(channel) for channel in group_names]
    center = split_center_x(obj)
    cols_of_group_index = {}
    for col, (name, side) in enumerate(channels):
        vg = obj.vertex_groups.get(name)
        if vg is not None:
            cols_of_group_index.setdefault(vg.index, []).append((col, side))

    mat = np.zeros((len(vert_indices), len(group_names)), dtype=np.float32)
    for row, vi in enumerate(vert_indices):
        x = verts[vi].co.x
        for g in verts[vi].groups:
            for col, side in cols_of_group_index.get(g.group, ()):
                if ((side == 'POS' and x < center)
                        or (side == 'NEG' and x >= center)):
                    continue
                mat[row, col] = g.weight
    return mat


def nonempty_group_names(obj, group_names, min_weight=1e-8):
    """Return names that have at least one vertex weight above ``min_weight``."""
    wanted = set(group_names)
    index_to_name = {vg.index: vg.name for vg in obj.vertex_groups
                     if vg.name in wanted}
    nonempty = set()
    for vertex in obj.data.vertices:
        for group in vertex.groups:
            if group.weight > min_weight:
                name = index_to_name.get(group.group)
                if name is not None:
                    nonempty.add(name)
    return [name for name in group_names if name in nonempty]


def target_deform_group_names(obj):
    """Target vertex groups that correspond to bones, when an armature exists.

    Metadata groups such as ``mmd_vertex_order`` must never be offered as a
    weight-matching destination.  Meshes without an armature retain all their
    groups for the generic mesh-to-mesh workflow.
    """
    armature = next((modifier.object for modifier in obj.modifiers
                     if modifier.type == 'ARMATURE' and modifier.object), None)
    if armature is None and obj.parent and obj.parent.type == 'ARMATURE':
        armature = obj.parent
    names = [vg.name for vg in obj.vertex_groups]
    if armature is None:
        return names
    bone_names = {bone.name for bone in armature.data.bones}
    deform = [name for name in names if name in bone_names]
    return deform if deform else names


def build_surface_bvh(mesh):
    """BVH over the mesh's loop triangles.

    Returns ``(bvh, tris, coords)`` where ``tris`` is a list of ``(a, b, c)``
    vertex-index triples aligned with the index returned by
    ``bvh.find_nearest()``.
    """
    mesh.calc_loop_triangles()
    tris = [tuple(t.vertices) for t in mesh.loop_triangles]
    coords = mesh_coords_np(mesh)
    bvh = BVHTree.FromPolygons([tuple(c) for c in coords], tris)
    return bvh, tris, coords


def sample_source_field(src_obj, tgt_obj, tgt_vert_indices, src_group_names):
    """Sample the source object's group weights onto target vertices.

    Target vertices are queried against the source surface in each object's
    LOCAL space, so the comparison is independent of where the two objects
    sit in the scene - it only assumes the two meshes line up in their own
    modeling space (true for re-rigged variants of the same base mesh).
    The closest surface point is found per vertex and the source group
    weights are interpolated there with barycentric coordinates.
    Returns an (N, Gs) float32 matrix; rows with no surface hit stay zero.
    """
    tgt_vert_indices = list(tgt_vert_indices)
    mesh = src_obj.data
    out = np.zeros((len(tgt_vert_indices), len(src_group_names)), dtype=np.float32)
    if not mesh.polygons or not tgt_vert_indices:
        return out

    bvh, tris, coords = build_surface_bvh(mesh)
    channels = [channel_parts(channel) for channel in src_group_names]
    center = split_center_x(src_obj)
    cols_of_group_index = {}
    for col, (name, side) in enumerate(channels):
        vg = src_obj.vertex_groups.get(name)
        if vg is not None:
            cols_of_group_index.setdefault(vg.index, []).append((col, side))

    query = mesh_coords_np(tgt_obj.data)[tgt_vert_indices]

    for i, co in enumerate(query):
        pt = Vector(co)
        hit = bvh.find_nearest(pt)
        if hit is None or hit[2] is None:
            continue
        loc, _nrm, tri_i, _dist = hit
        a, b, c = tris[tri_i]
        bary = poly_3d_calc(
            (Vector(coords[a]), Vector(coords[b]), Vector(coords[c])), loc)
        for factor, vi in zip(bary, (a, b, c)):
            if factor == 0.0:
                continue
            for group in mesh.vertices[vi].groups:
                for col, side in cols_of_group_index.get(group.group, ()):
                    x = coords[vi, 0]
                    if ((side == 'POS' and x < center)
                            or (side == 'NEG' and x >= center)):
                        continue
                    out[i, col] += factor * group.weight
    return out


def group_centroids(obj, group_names, vert_indices=None, min_weight=0.01):
    """Weighted centroid per group in the object's LOCAL space.

    Local space keeps the comparison translation-invariant, so it does not
    matter where the two meshes sit in the scene.  Returns
    ``({col: Vector}, bbox_diagonal)`` where ``bbox_diagonal`` is the local
    bounding-box diagonal, used to normalize distances between differently
    sized models.
    """
    mesh = obj.data
    coords = mesh_coords_np(mesh)

    channels = [channel_parts(channel) for channel in group_names]
    center = split_center_x(obj)
    cols_of_group_index = {}
    for col, (name, side) in enumerate(channels):
        vg = obj.vertex_groups.get(name)
        if vg is not None:
            cols_of_group_index.setdefault(vg.index, []).append((col, side))

    sums = np.zeros((len(group_names), 4), dtype=np.float64)
    verts = mesh.vertices
    if vert_indices is None:
        vert_indices = range(len(verts))
    for vi in vert_indices:
        x, y, z = coords[vi]
        for g in verts[vi].groups:
            for col, side in cols_of_group_index.get(g.group, ()):
                if ((side == 'POS' and x < center)
                        or (side == 'NEG' and x >= center)):
                    continue
                w = g.weight
                if w > min_weight:
                    sums[col, 0] += x * w
                    sums[col, 1] += y * w
                    sums[col, 2] += z * w
                    sums[col, 3] += w

    diag = 1e-9
    if len(coords):
        diag = max(float(np.linalg.norm(coords.max(axis=0) - coords.min(axis=0))), 1e-9)

    centroids = {}
    for col in range(len(group_names)):
        if sums[col, 3] > 0.0:
            centroids[col] = Vector(sums[col, :3]) / sums[col, 3]
    return centroids, diag


def centroid_similarity_matrix(src_centroids, tgt_centroids, n_src, n_tgt, diag):
    """Convert normalized centroid distance to a linear 0..1 similarity.

    A distance of one bounding-box diagonal (or more) scores zero.  Unlike the
    old reciprocal curve, this lets ordinary thresholds below 0.5 actually
    reject spatially distant groups on aligned meshes.
    """
    sim = np.zeros((n_src, n_tgt), dtype=np.float32)
    for s, cs in src_centroids.items():
        for t, ct in tgt_centroids.items():
            dist = (cs - ct).length / diag
            sim[s, t] = max(0.0, 1.0 - dist)
    return sim


def match_by_name(src_names, tgt_names, allow_merge=False):
    """Match names after normalization, preferring exact-name pairs.

    In one-to-one mode duplicate normalized names consume distinct matching
    targets instead of silently mapping several sources onto the same group.
    """
    result = {}
    used_tgt = set()

    # Preserve exact names first when punctuation-normalized names collide.
    for s, name in enumerate(src_names):
        for t, target_name in enumerate(tgt_names):
            if target_name == name and (allow_merge or t not in used_tgt):
                result[s] = (t, 1.0)
                used_tgt.add(t)
                break

    tgt_lookup = {}
    for t, name in enumerate(tgt_names):
        key = normalized_name(name)
        if key:
            tgt_lookup.setdefault(key, []).append(t)
    for s, name in enumerate(src_names):
        if s in result:
            continue
        key = normalized_name(name)
        candidates = tgt_lookup.get(key, ()) if key else ()
        t = next((t for t in candidates if allow_merge or t not in used_tgt), None)
        if t is not None:
            result[s] = (t, 1.0)
            used_tgt.add(t)
    return result
