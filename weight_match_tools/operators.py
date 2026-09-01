"""Operators: auto matching, apply rename/merge, weight transfer, CSV export."""

import csv
import time

import bpy
import numpy as np
from bpy.props import StringProperty

from . import matching
from .i18n import register_rna_class, tr, unregister_rna_class
from .similarity import (complete_assignment, cosine_similarity_matrix,
                         optimal_assignment, subsample_indices)


def _group_names(obj):
    return [vg.name for vg in obj.vertex_groups]


def _target_group_names(obj):
    return matching.target_deform_group_names(obj)


def _active_pairs(settings):
    """Enabled ``(source_name, spatial_half, target_or_None)`` rows."""
    pairs = []
    for item in settings.items:
        if not item.enabled:
            continue
        target = item.target_name
        pairs.append((item.source_name, item.source_side,
                      target if target else None))
    return pairs


def _pair_parts(pair):
    """Accept current triples and legacy internal two-tuples."""
    if len(pair) == 3:
        return pair[0], pair[1] or "", pair[2]
    return pair[0], "", pair[1]


def _unmatched_nonempty_groups(src, tgt, pairs):
    """Weighted source groups that would survive outside the target template."""
    target_names = set(_group_names(tgt))
    nonempty = matching.nonempty_group_names(src, _group_names(src))
    expected = {}
    for name, side in matching.source_group_channels(src, nonempty):
        expected.setdefault(name, set()).add(side)
    actual = {}
    for pair in pairs:
        src_name, side, tgt_name = _pair_parts(pair)
        if tgt_name in target_names:
            actual.setdefault(src_name, set()).add(side)
    assigned = {name for name, sides in expected.items()
                if sides.issubset(actual.get(name, set()))}
    return [name for name in nonempty
            if name not in target_names and name not in assigned]


def _target_vertex_ids(obj, selected_only):
    mesh = obj.data
    if selected_only:
        ids = [v.index for v in mesh.vertices if v.select]
        if ids:
            return ids
    return list(range(len(mesh.vertices)))


def _reorder_vertex_groups(obj, ordered_names):
    """Rebuild the object's vertex groups in the given name order.

    Groups absent from ``ordered_names`` keep their relative order at the
    end.  Weights are re-assigned by name, so armature bindings (which
    reference names, not indices) are unaffected.  Returns True if the
    order changed.
    """
    current = [vg.name for vg in obj.vertex_groups]
    wanted = set(ordered_names)
    new_order = ([n for n in ordered_names if n in current]
                 + [n for n in current if n not in wanted])
    if new_order == current:
        return False

    me = obj.data
    name_of_index = {vg.index: vg.name for vg in obj.vertex_groups}
    weights = {name: [] for name in current}
    for v in me.vertices:
        vi = v.index
        for g in v.groups:
            name = name_of_index.get(g.group)
            if name is not None:
                weights[name].append((vi, g.weight))

    for vg in list(obj.vertex_groups):
        obj.vertex_groups.remove(vg)
    for name in new_order:
        vg = obj.vertex_groups.new(name=name)
        for vi, w in weights[name]:
            vg.add([vi], w, 'REPLACE')
    return True


def _compute_assignment(src, tgt, s):
    """Match src's groups against tgt's with the given settings.

    Returns (src_channels, tgt_names, assignment, force_filled) where assignment
    maps a source column index to (target column index, similarity) and
    force_filled counts pairs added by Match All (Force).
    """
    if s.match_mode == 'NAME':
        src_channels = [(name, '') for name in _group_names(src)]
        tgt_names = _target_group_names(tgt)
    else:
        src_names = matching.nonempty_group_names(src, _group_names(src))
        src_channels = matching.source_group_channels(src, src_names)
        tgt_names = matching.nonempty_group_names(tgt, _target_group_names(tgt))
    assignment = {}
    sim = None

    if s.match_mode == 'NAME':
        assignment.update(matching.match_by_name(
            [name for name, _side in src_channels], tgt_names, s.allow_merge))
    elif s.match_mode == 'CENTROID':
        src_cents, diag_s = matching.group_centroids(
            src, src_channels, min_weight=s.min_weight)
        tgt_cents, diag_t = matching.group_centroids(
            tgt, tgt_names, min_weight=s.min_weight)
        sim = matching.centroid_similarity_matrix(
            src_cents, tgt_cents, len(src_channels), len(tgt_names),
            max(diag_s, diag_t))
        sim = matching.apply_side_bias(sim, src_channels, tgt_names)
        assignment.update(optimal_assignment(
            sim, s.similarity_threshold, s.allow_merge))
    else:  # WEIGHT
        selected_target_ids = (_target_vertex_ids(tgt, True)
                               if s.use_selected_only else [])
        target_has_selection = (s.use_selected_only
                                and len(selected_target_ids) < len(tgt.data.vertices))
        if target_has_selection:
            # Preserve the explicit selected-target workflow.
            vert_ids = subsample_indices(selected_target_ids, s.sample_limit)
            src_field = matching.sample_source_field(
                src, tgt, vert_ids, src_channels)
            tgt_field = matching.weight_matrix(tgt, tgt_names, vert_ids)
        else:
            # For a partial garment against a full body, compare only where
            # the garment actually has vertices instead of extrapolating its
            # nearest surface across the entire body.
            vert_ids = subsample_indices(
                range(len(src.data.vertices)), s.sample_limit)
            src_field = matching.weight_matrix(src, src_channels, vert_ids)
            tgt_field = matching.sample_source_field(
                tgt, src, vert_ids, tgt_names)
        sim = cosine_similarity_matrix(src_field, tgt_field)
        src_cents, diag_s = matching.group_centroids(src, src_channels)
        tgt_cents, diag_t = matching.group_centroids(tgt, tgt_names)
        spatial = matching.centroid_similarity_matrix(
            src_cents, tgt_cents, len(src_channels), len(tgt_names),
            max(diag_s, diag_t))
        # Spatial position is a tiebreaker, not a replacement for overlap.
        sim = np.clip(sim + (1.0 - sim) * 0.05 * spatial, 0.0, 1.0)
        sim = matching.apply_side_bias(sim, src_channels, tgt_names)
        assignment.update(optimal_assignment(
            sim, s.similarity_threshold, s.allow_merge))

    force_filled = 0
    if s.force_match_all:
        before = len(assignment)
        if sim is None:  # NAME mode: no similarity signal, fill arbitrarily
            sim = np.zeros((len(src_channels), len(tgt_names)), dtype=np.float32)
        complete_assignment(sim, assignment, s.allow_merge)
        force_filled = len(assignment) - before
    return src_channels, tgt_names, assignment, force_filled


def _write_items(s, src_channels, tgt_names, assignment):
    """Fill the mapping table from an assignment dict."""
    s.items.clear()
    for si, channel in enumerate(src_channels):
        name, side = matching.channel_parts(channel)
        item = s.items.add()
        item.source_name = name
        item.source_side = side
        hit = assignment.get(si)
        if hit is not None:
            ti, score = hit
            item.target_enum = tgt_names[ti]
            item.similarity = float(score)


class WEIGHTMATCH_OT_auto_match(bpy.types.Operator):
    bl_idname = "weight_match.auto_match"
    bl_label = tr("Auto Match Groups")
    bl_description = tr("Guess which source vertex group corresponds to which "
                        "target vertex group and fill the mapping table")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        s = context.scene.weight_match
        return (s.source_object is not None
                and s.target_object is not None
                and s.source_object != s.target_object)

    def execute(self, context):
        s = context.scene.weight_match
        src, tgt = s.source_object, s.target_object
        if not _group_names(src):
            self.report({'WARNING'}, "Source object has no vertex groups")
            return {'CANCELLED'}
        if not _group_names(tgt):
            self.report({'WARNING'}, "Target object has no vertex groups")
            return {'CANCELLED'}

        t0 = time.time()
        src_channels, tgt_names, assignment, force_filled = \
            _compute_assignment(src, tgt, s)
        if not src_channels:
            self.report({'WARNING'}, "Source object has no weighted vertex groups")
            return {'CANCELLED'}
        if not tgt_names:
            self.report({'WARNING'}, "Target object has no weighted deform groups")
            return {'CANCELLED'}

        _write_items(s, src_channels, tgt_names, assignment)

        matched = sum(1 for it in s.items if it.target_name)
        split_count = len(src_channels) - len({name for name, _ in src_channels})
        msg = (f"Matched {matched}/{len(src_channels)} source channels "
               f"in {time.time() - t0:.2f}s ({s.match_mode} mode)")
        if split_count:
            msg += f", spatially split {split_count} bilateral groups"
        if force_filled:
            msg += f", force-filled {force_filled} without a strong match"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


def _apply_mapping(src, tgt_obj, pairs):
    """Rename/merge source channels, splitting bilateral groups when needed.

    Empty source-only groups are removed, then every target group is created
    and ordered exactly like the target template.  Returns
    ``(renamed, merged, kept, removed_empty, created, reordered)``.
    """
    me = src.data
    pairs = [_pair_parts(pair) for pair in pairs]

    # Snapshot each involved source group once.  A bilateral group can occur
    # in two mapping rows, so renaming the first row in-place would make the
    # second row disappear.  Rebuilding temporary channel groups from this
    # snapshot also lets us partition the weights at the mesh's X center.
    involved = {src_name for src_name, _side, _target in pairs}
    index_to_name = {vg.index: vg.name for vg in src.vertex_groups
                     if vg.name in involved}
    snapshots = {name: [] for name in involved if src.vertex_groups.get(name)}
    for vertex in me.vertices:
        for element in vertex.groups:
            name = index_to_name.get(element.group)
            if name is not None:
                snapshots[name].append((vertex.index, element.weight))
    for name in snapshots:
        vg = src.vertex_groups.get(name)
        if vg is not None:
            src.vertex_groups.remove(vg)

    used = {vg.name for vg in src.vertex_groups}
    staged = []  # (temp_name, original_name, target_name_or_None)
    center = matching.split_center_x(src)
    for i, (src_name, side, tgt_name) in enumerate(pairs):
        weights = snapshots.get(src_name)
        if weights is None:
            continue
        temp = f"__wmt_{i}"
        while temp in used:
            temp += "_"
        vg = src.vertex_groups.new(name=temp)
        for vi, weight in weights:
            x = me.vertices[vi].co.x
            if ((side == 'POS' and x < center)
                    or (side == 'NEG' and x >= center)):
                continue
            vg.add([vi], weight, 'REPLACE')
        used.add(temp)
        staged.append((temp, src_name, tgt_name))

    renamed = merged = kept = 0
    for temp, orig, tgt_name in staged:
        vg = src.vertex_groups.get(temp)
        final = tgt_name if tgt_name else orig
        existing = src.vertex_groups.get(final)
        if existing is None:
            vg.name = final
            if final == orig:
                kept += 1
            else:
                renamed += 1
        else:
            # A group with the final name already exists (either another
            # staged group claimed it first, or it was never staged):
            # union the weights.
            for v in me.vertices:
                for g in v.groups:
                    if g.group == vg.index:
                        existing.add([v.index], g.weight, 'ADD')
            src.vertex_groups.remove(vg)
            merged += 1

    target_names = _group_names(tgt_obj)
    target_set = set(target_names)
    current_names = _group_names(src)
    nonempty = set(matching.nonempty_group_names(src, current_names))
    removed_empty = 0
    for vg in list(src.vertex_groups):
        if vg.name not in target_set and vg.name not in nonempty:
            src.vertex_groups.remove(vg)
            removed_empty += 1

    created = 0
    for name in target_names:
        if src.vertex_groups.get(name) is None:
            src.vertex_groups.new(name=name)
            created += 1

    reordered = _reorder_vertex_groups(src, target_names)
    if _group_names(src) != target_names:
        raise RuntimeError(
            "Source still has non-target weighted groups after applying mapping")
    return renamed, merged, kept, removed_empty, created, reordered


class WEIGHTMATCH_OT_apply_rename(bpy.types.Operator):
    bl_idname = "weight_match.apply_rename"
    bl_label = tr("Apply to Source (Rename/Merge)")
    bl_description = tr("Rename the source object's vertex groups to the matched "
                        "target names, merging weights where names collide, and "
                        "create empty groups for missing target groups")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        s = context.scene.weight_match
        return (s.source_object is not None and s.target_object is not None
                and s.source_object != s.target_object)

    def execute(self, context):
        s = context.scene.weight_match
        pairs = _active_pairs(s)
        if not pairs:
            self.report({'WARNING'}, "Mapping table is empty - run Auto Match first")
            return {'CANCELLED'}

        unmatched = _unmatched_nonempty_groups(
            s.source_object, s.target_object, pairs)
        if unmatched:
            preview = ", ".join(unmatched[:5])
            self.report(
                {'ERROR'},
                f"{len(unmatched)} weighted groups are unmatched ({preview}). "
                "Enable Match All (Force) or assign them manually first")
            return {'CANCELLED'}

        renamed, merged, kept, removed, created, reordered = _apply_mapping(
            s.source_object, s.target_object, pairs)

        msg = (f"Renamed {renamed}, merged {merged}, kept {kept} groups; "
               f"removed {removed} old empty groups; "
               f"created {created} target groups")
        if reordered:
            msg += "; reordered to target order"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class WEIGHTMATCH_OT_batch_match(bpy.types.Operator):
    bl_idname = "weight_match.batch_match"
    bl_label = tr("Batch Match Selected")
    bl_description = tr("Run Auto Match + Apply on every selected mesh (except "
                        "the target) against the target object, using the "
                        "current matching settings")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        s = context.scene.weight_match
        return s.target_object is not None and bool(context.selected_objects)

    def execute(self, context):
        s = context.scene.weight_match
        tgt = s.target_object
        if not _group_names(tgt):
            self.report({'WARNING'}, "Target object has no vertex groups")
            return {'CANCELLED'}

        # view_layer scan instead of context.selected_objects: the latter can
        # lag behind select_set() until the depsgraph re-evaluates.
        sources = [o for o in context.view_layer.objects
                   if o.select_get() and o.type == 'MESH' and o != tgt]
        if not sources:
            self.report({'WARNING'},
                        "Select the mesh objects to match (the target is skipped)")
            return {'CANCELLED'}
        sources.sort(key=lambda o: o.name)

        t0 = time.time()
        lines = []
        for src in sources:
            if not _group_names(src):
                lines.append(f"{src.name}: skipped (no vertex groups)")
                continue
            src_channels, tgt_names, assignment, _ = _compute_assignment(
                src, tgt, s)
            if not src_channels:
                lines.append(f"{src.name}: skipped (no weighted vertex groups)")
                continue
            pairs = [(name, side,
                      tgt_names[assignment[si][0]] if si in assignment else None)
                     for si, (name, side) in enumerate(src_channels)]
            unmatched = _unmatched_nonempty_groups(src, tgt, pairs)
            if unmatched:
                lines.append(
                    f"{src.name}: skipped ({len(unmatched)} weighted groups unmatched)")
                continue
            renamed, merged, kept, removed, created, reordered = _apply_mapping(
                src, tgt, pairs)
            lines.append(f"{src.name}: renamed {renamed}, merged {merged}, "
                         f"removed {removed} old empty, created {created}")

        # Leave the table showing a fresh mapping for the last source.  It has
        # already been rebuilt to the exact target template, which is useful
        # confirmation that the batch Apply completed successfully.
        if sources:
            last = sources[-1]
            if _group_names(last):
                last_channels, target_names, assignment, _ = \
                    _compute_assignment(last, tgt, s)
                _write_items(s, last_channels, target_names, assignment)
                s.source_object = last

        msg = (f"Batch matched {len(sources)} objects in "
               f"{time.time() - t0:.1f}s\n" + "\n".join(lines))
        print(msg)
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class WEIGHTMATCH_OT_transfer_weights(bpy.types.Operator):
    bl_idname = "weight_match.transfer_weights"
    bl_label = tr("Transfer Weights to Target")
    bl_description = tr("Write the source groups' weights onto the target mesh "
                        "using the mapping table (surface sampling, so it works "
                        "across different topology)")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        s = context.scene.weight_match
        return (s.source_object is not None
                and s.target_object is not None
                and s.source_object != s.target_object)

    def execute(self, context):
        s = context.scene.weight_match
        src, tgt = s.source_object, s.target_object
        pairs = [(src_n, side, tgt_n)
                 for src_n, side, tgt_n in _active_pairs(s) if tgt_n]
        if not pairs:
            self.report({'WARNING'},
                        "No enabled rows with a target group - run Auto Match first")
            return {'CANCELLED'}

        t0 = time.time()
        # Before Apply, a repeated source name may represent two spatial
        # channels.  After Apply, fall back to the already-created target
        # groups and sample each of those as an ordinary whole group.
        channels = []
        resolved = []
        for src_name, side, tgt_name in pairs:
            if src.vertex_groups.get(src_name) is not None:
                channel = (src_name, side)
            elif src.vertex_groups.get(tgt_name) is not None:
                channel = (tgt_name, '')
            else:
                continue
            channels.append(channel)
            resolved.append((channel, tgt_name))

        vert_ids = _target_vertex_ids(tgt, s.use_selected_only)
        field = matching.sample_source_field(src, tgt, vert_ids, channels)

        # Many-to-one mappings: several source columns can feed the same
        # target group.  Combine them per vertex (clamped to 1) so nothing
        # is lost - a plain per-row REPLACE would let the last row win.
        combined = {}
        seen = set()
        for col, (channel, tgt_name) in enumerate(resolved):
            contribution = (channel, tgt_name)
            # Several pre-Apply source rows can collapse to the same target
            # group.  Once Apply has merged them, the fallback channel is the
            # same and must only be counted once on a later Transfer.
            if contribution in seen:
                continue
            seen.add(contribution)
            if tgt_name in combined:
                combined[tgt_name] += field[:, col]
            else:
                combined[tgt_name] = field[:, col].copy()

        # Existing membership per group index, so stale weights can be
        # overwritten with explicit zeros.
        members = {}
        for v in tgt.data.vertices:
            for g in v.groups:
                members.setdefault(g.group, set()).add(v.index)

        written_groups = 0
        affected = set()
        for tgt_name, column in combined.items():
            vg = tgt.vertex_groups.get(tgt_name)
            if vg is None:
                vg = tgt.vertex_groups.new(name=tgt_name)
            mem = members.get(vg.index, ())
            count = 0
            for row, vi in enumerate(vert_ids):
                w = min(1.0, float(column[row]))
                if w > 1e-6 or vi in mem:
                    vg.add([vi], w, 'REPLACE')
                    count += 1
            if count:
                written_groups += 1
                affected.update(vert_ids)

        normalized = 0
        if s.normalize_after and affected:
            verts = tgt.data.vertices
            for vi in affected:
                elements = verts[vi].groups
                total = 0.0
                for g in elements:
                    total += g.weight
                if total > 1e-9 and abs(total - 1.0) > 1e-6:
                    inv = 1.0 / total
                    for g in elements:
                        g.weight = min(1.0, g.weight * inv)
                    normalized += 1

        self.report(
            {'INFO'},
            f"Wrote {written_groups} groups on {len(affected)} vertices "
            f"in {time.time() - t0:.2f}s"
            + (f", normalized {normalized} vertices" if normalized else ""))
        return {'FINISHED'}


class WEIGHTMATCH_OT_export_csv(bpy.types.Operator):
    bl_idname = "weight_match.export_csv"
    bl_label = tr("Export Mapping (CSV)")
    bl_description = tr("Save the current mapping table as a CSV file")

    filepath: StringProperty(
        name=tr("File Path"),
        description=tr("Where to save the CSV"),
        default="weight_mapping.csv",
        subtype='FILE_PATH',
    )

    def invoke(self, context, _event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        s = context.scene.weight_match
        if not self.filepath.lower().endswith('.csv'):
            self.filepath += '.csv'
        with open(self.filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["source", "source_half", "target",
                             "similarity", "enabled"])
            for item in s.items:
                writer.writerow([item.source_name,
                                 item.source_side,
                                 item.target_name or "(keep)",
                                 f"{item.similarity:.4f}",
                                 int(item.enabled)])
        self.report({'INFO'}, f"Saved {len(s.items)} rows to {self.filepath}")
        return {'FINISHED'}


class WEIGHTMATCH_OT_clear_mapping(bpy.types.Operator):
    bl_idname = "weight_match.clear_mapping"
    bl_label = tr("Clear Mapping")
    bl_description = tr("Empty the mapping table")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        context.scene.weight_match.items.clear()
        return {'FINISHED'}


classes = (
    WEIGHTMATCH_OT_auto_match,
    WEIGHTMATCH_OT_batch_match,
    WEIGHTMATCH_OT_apply_rename,
    WEIGHTMATCH_OT_transfer_weights,
    WEIGHTMATCH_OT_export_csv,
    WEIGHTMATCH_OT_clear_mapping,
)


def register():
    for cls in classes:
        register_rna_class(cls)


def unregister():
    for cls in reversed(classes):
        unregister_rna_class(cls)
