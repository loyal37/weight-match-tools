"""Weight-field extraction, surface sampling and spatial matching.

Spatial comparisons happen in each object's LOCAL space, so they are
independent of where the meshes sit in the scene; they assume the two meshes
line up in their own modeling space (re-rigged variants of the same base
mesh), which is the typical rename/transfer workflow.
"""

import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.interpolate import poly_3d_calc

from .similarity import normalized_name


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

    col_of_group_index = {}
    for col, name in enumerate(group_names):
        vg = obj.vertex_groups.get(name)
        if vg is not None:
            col_of_group_index[vg.index] = col

    mat = np.zeros((len(vert_indices), len(group_names)), dtype=np.float32)
    for row, vi in enumerate(vert_indices):
        for g in verts[vi].groups:
            col = col_of_group_index.get(g.group)
            if col is not None:
                mat[row, col] = g.weight
    return mat


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
    weights = weight_matrix(src_obj, src_group_names)

    query = mesh_coords_np(tgt_obj.data)[tgt_vert_indices]

    for i, co in enumerate(query):
        pt = Vector(co)
        hit = bvh.find_nearest(pt)
        if hit is None or hit[2] is None:
            continue
        _loc, _nrm, tri_i, _dist = hit
        a, b, c = tris[tri_i]
        bary = poly_3d_calc((Vector(coords[a]), Vector(coords[b]), Vector(coords[c])), pt)
        out[i] = bary[0] * weights[a] + bary[1] * weights[b] + bary[2] * weights[c]
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

    col_of_group_index = {}
    for col, name in enumerate(group_names):
        vg = obj.vertex_groups.get(name)
        if vg is not None:
            col_of_group_index[vg.index] = col

    sums = np.zeros((len(group_names), 4), dtype=np.float64)
    verts = mesh.vertices
    if vert_indices is None:
        vert_indices = range(len(verts))
    for vi in vert_indices:
        x, y, z = coords[vi]
        for g in verts[vi].groups:
            col = col_of_group_index.get(g.group)
            if col is not None:
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
    """Convert centroid distances to a 0..1 similarity: 1 / (1 + dist/diag)."""
    sim = np.zeros((n_src, n_tgt), dtype=np.float32)
    for s, cs in src_centroids.items():
        for t, ct in tgt_centroids.items():
            dist = (cs - ct).length / diag
            sim[s, t] = 1.0 / (1.0 + dist)
    return sim


def match_by_name(src_names, tgt_names):
    """Match names after normalization.  Returns ``{src_col: (tgt_col, 1.0)}``."""
    tgt_lookup = {}
    for t, name in enumerate(tgt_names):
        tgt_lookup.setdefault(normalized_name(name), t)
    result = {}
    for s, name in enumerate(src_names):
        t = tgt_lookup.get(normalized_name(name))
        if t is not None:
            result[s] = (t, 1.0)
    return result
