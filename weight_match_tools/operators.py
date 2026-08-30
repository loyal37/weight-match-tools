"""Operators: auto matching, apply rename/merge, weight transfer, CSV export."""

import csv
import time

import bpy
from bpy.props import StringProperty

from . import matching
from .similarity import cosine_similarity_matrix, greedy_assignment, subsample_indices


def _group_names(obj):
    return [vg.name for vg in obj.vertex_groups]


def _active_pairs(settings):
    """(source_name, target_name_or_None) for enabled rows, in list order."""
    pairs = []
    for item in settings.items:
        if not item.enabled:
            continue
        target = item.target_name
        pairs.append((item.source_name, target if target else None))
    return pairs


def _target_vertex_ids(obj, selected_only):
    mesh = obj.data
    if selected_only:
        ids = [v.index for v in mesh.vertices if v.select]
        if ids:
            return ids
    return list(range(len(mesh.vertices)))


class WEIGHTMATCH_OT_auto_match(bpy.types.Operator):
    bl_idname = "weight_match.auto_match"
    bl_label = "Auto Match Groups"
    bl_description = "Guess which source vertex group corresponds to which " \
                     "target vertex group and fill the mapping table"
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
        src_names = _group_names(src)
        tgt_names = _group_names(tgt)
        if not src_names:
            self.report({'WARNING'}, "Source object has no vertex groups")
            return {'CANCELLED'}
        if not tgt_names:
            self.report({'WARNING'}, "Target object has no vertex groups")
            return {'CANCELLED'}

        t0 = time.time()
        assignment = {}
        locked_src, locked_tgt = set(), set()
        if s.match_mode != 'NAME' and s.prefer_same_name:
            for si, name in enumerate(src_names):
                if name in tgt_names:
                    ti = tgt_names.index(name)
                    assignment[si] = (ti, 1.0)
                    locked_src.add(si)
                    locked_tgt.add(ti)

        if s.match_mode == 'NAME':
            assignment.update(matching.match_by_name(src_names, tgt_names))
        elif s.match_mode == 'CENTROID':
            src_cents, diag_s = matching.group_centroids(
                src, src_names, min_weight=s.min_weight)
            tgt_cents, diag_t = matching.group_centroids(
                tgt, tgt_names, min_weight=s.min_weight)
            sim = matching.centroid_similarity_matrix(
                src_cents, tgt_cents, len(src_names), len(tgt_names),
                max(diag_s, diag_t))
            assignment.update(greedy_assignment(
                sim, s.similarity_threshold, s.allow_merge,
                locked_src, locked_tgt))
        else:  # WEIGHT
            vert_ids = subsample_indices(
                _target_vertex_ids(tgt, s.use_selected_only), s.sample_limit)
            src_field = matching.sample_source_field(src, tgt, vert_ids, src_names)
            tgt_field = matching.weight_matrix(tgt, tgt_names, vert_ids)
            sim = cosine_similarity_matrix(src_field, tgt_field)
            assignment.update(greedy_assignment(
                sim, s.similarity_threshold, s.allow_merge,
                locked_src, locked_tgt))

        s.items.clear()
        for si, name in enumerate(src_names):
            item = s.items.add()
            item.source_name = name
            hit = assignment.get(si)
            if hit is not None:
                ti, score = hit
                item.target_enum = tgt_names[ti]
                item.similarity = float(score)

        matched = sum(1 for it in s.items if it.target_name)
        self.report(
            {'INFO'},
            f"Matched {matched}/{len(src_names)} source groups "
            f"in {time.time() - t0:.2f}s ({s.match_mode} mode)")
        return {'FINISHED'}


class WEIGHTMATCH_OT_apply_rename(bpy.types.Operator):
    bl_idname = "weight_match.apply_rename"
    bl_label = "Apply to Source (Rename/Merge)"
    bl_description = "Rename the source object's vertex groups to the matched " \
                     "target names, merging weights where names collide, and " \
                     "create empty groups for missing target groups"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene.weight_match.source_object is not None

    def execute(self, context):
        s = context.scene.weight_match
        src = s.source_object
        me = src.data
        pairs = _active_pairs(s)
        if not pairs:
            self.report({'WARNING'}, "Mapping table is empty - run Auto Match first")
            return {'CANCELLED'}

        # Phase 1: move every involved source group out of the way with a temp
        # name so renames can never collide with names still waiting to be
        # merged into.
        used = {vg.name for vg in src.vertex_groups}
        staged = []  # (temp_name, original_name, target_name_or_None)
        for i, (src_name, tgt_name) in enumerate(pairs):
            vg = src.vertex_groups.get(src_name)
            if vg is None:
                continue
            temp = f"__wmt_{i}"
            while temp in used:
                temp += "_"
            vg.name = temp
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

        created = 0
        if s.create_missing and s.target_object is not None:
            for tgt_vg in s.target_object.vertex_groups:
                if src.vertex_groups.get(tgt_vg.name) is None:
                    src.vertex_groups.new(name=tgt_vg.name)
                    created += 1

        self.report(
            {'INFO'},
            f"Renamed {renamed}, merged {merged}, kept {kept} groups; "
            f"created {created} empty groups")
        return {'FINISHED'}


class WEIGHTMATCH_OT_transfer_weights(bpy.types.Operator):
    bl_idname = "weight_match.transfer_weights"
    bl_label = "Transfer Weights to Target"
    bl_description = "Write the source groups' weights onto the target mesh " \
                     "using the mapping table (surface sampling, so it works " \
                     "across different topology)"
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
        pairs = [(src_n, tgt_n) for src_n, tgt_n in _active_pairs(s) if tgt_n]
        if not pairs:
            self.report({'WARNING'},
                        "No enabled rows with a target group - run Auto Match first")
            return {'CANCELLED'}

        t0 = time.time()
        src_names = _group_names(src)
        col_of_src = {name: i for i, name in enumerate(src_names)}

        vert_ids = _target_vertex_ids(tgt, s.use_selected_only)
        field = matching.sample_source_field(src, tgt, vert_ids, src_names)

        # Existing membership per group index, so stale weights can be
        # overwritten with explicit zeros.
        members = {}
        for v in tgt.data.vertices:
            for g in v.groups:
                members.setdefault(g.group, set()).add(v.index)

        written_groups = 0
        affected = set()
        for src_name, tgt_name in pairs:
            col = col_of_src.get(src_name)
            if col is None and tgt_name:
                # After "Apply to Source" the groups already carry the target
                # names, so the same mapping keeps working via the new name.
                col = col_of_src.get(tgt_name)
            if col is None:
                continue
            column = field[:, col]
            vg = tgt.vertex_groups.get(tgt_name)
            if vg is None:
                vg = tgt.vertex_groups.new(name=tgt_name)
            mem = members.get(vg.index, ())
            count = 0
            for row, vi in enumerate(vert_ids):
                w = float(column[row])
                if w > 1e-6 or vi in mem:
                    vg.add([vi], min(1.0, w), 'REPLACE')
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
    bl_label = "Export Mapping (CSV)"
    bl_description = "Save the current mapping table as a CSV file"

    filepath: StringProperty(
        name="File Path",
        description="Where to save the CSV",
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
            writer.writerow(["source", "target", "similarity", "enabled"])
            for item in s.items:
                writer.writerow([item.source_name,
                                 item.target_name or "(keep)",
                                 f"{item.similarity:.4f}",
                                 int(item.enabled)])
        self.report({'INFO'}, f"Saved {len(s.items)} rows to {self.filepath}")
        return {'FINISHED'}


class WEIGHTMATCH_OT_clear_mapping(bpy.types.Operator):
    bl_idname = "weight_match.clear_mapping"
    bl_label = "Clear Mapping"
    bl_description = "Empty the mapping table"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        context.scene.weight_match.items.clear()
        return {'FINISHED'}


classes = (
    WEIGHTMATCH_OT_auto_match,
    WEIGHTMATCH_OT_apply_rename,
    WEIGHTMATCH_OT_transfer_weights,
    WEIGHTMATCH_OT_export_csv,
    WEIGHTMATCH_OT_clear_mapping,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
