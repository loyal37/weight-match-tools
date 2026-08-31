"""Scene-level settings and mapping-row storage for Weight Match Tools."""

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)

from .i18n import tr

# Sentinel target value meaning "leave the source group's name unchanged".
KEEP = "__KEEP__"


def _poll_mesh_object(self, obj):
    return obj.type == 'MESH'


def _target_group_items(self, context):
    """Dynamic enum listing the target object's vertex groups."""
    items = [(KEEP, tr("(keep name)"),
              tr("Leave this source group's name unchanged"))]
    try:
        settings = context.scene.weight_match
        target = settings.target_object
        if target is not None:
            for vg in target.vertex_groups:
                items.append((vg.name, vg.name, ""))
    except Exception:
        pass
    return items


def _update_target_enum(self, context):
    self.target_name = "" if self.target_enum == KEEP else self.target_enum


class WeightMatchItem(bpy.types.PropertyGroup):
    """One row of the source -> target mapping table."""

    source_name: StringProperty(name=tr("Source Group"))
    target_name: StringProperty(name=tr("Target Group"))
    target_enum: EnumProperty(
        name=tr("Target Group"),
        description=tr("Which target vertex group this source group becomes"),
        items=_target_group_items,
        update=_update_target_enum,
    )
    similarity: FloatProperty(
        name=tr("Similarity"),
        description=tr("How well the two weight fields agree (1 = identical)"),
        default=0.0,
        min=0.0,
        max=1.0,
        subtype='FACTOR',
    )
    enabled: BoolProperty(
        name=tr("Apply"),
        description=tr("Include this row when applying or transferring"),
        default=True,
    )


class WeightMatchSettings(bpy.types.PropertyGroup):
    source_object: PointerProperty(
        name=tr("Source"),
        description=tr("Mesh whose vertex groups will be renamed/merged, "
                       "and whose weights are read from"),
        type=bpy.types.Object,
        poll=_poll_mesh_object,
    )
    target_object: PointerProperty(
        name=tr("Target"),
        description=tr("Mesh providing the destination naming "
                       "(usually the rigged model you want weights to end up on)"),
        type=bpy.types.Object,
        poll=_poll_mesh_object,
    )

    match_mode: EnumProperty(
        name=tr("Match Mode"),
        items=(
            ('WEIGHT', tr("Weight Field"),
             tr("Sample each source group's weights onto the target surface "
                "and compare against the target groups' weight fields "
                "(most accurate, recommended)")),
            ('CENTROID', tr("Spatial Centroid"),
             tr("Match each group's weighted average position "
                "(fast; good when weight fields are close to uniform)")),
            ('NAME', tr("Name Only"),
             tr("Match names after cleanup (case/punctuation ignored); "
                "no spatial test")),
        ),
        default='WEIGHT',
    )
    similarity_threshold: FloatProperty(
        name=tr("Min Similarity"),
        description=tr("Pairs below this similarity are left unmatched"),
        default=0.35,
        min=0.0,
        max=1.0,
        subtype='FACTOR',
    )
    prefer_same_name: BoolProperty(
        name=tr("Lock Same Names"),
        description=tr("Groups whose names are identical on both sides are "
                       "matched first and excluded from automatic assignment"),
        default=True,
    )
    allow_merge: BoolProperty(
        name=tr("Allow Many-to-One"),
        description=tr("Let several source groups match the same target group "
                       "(their weights are merged on Apply)"),
        default=False,
    )
    force_match_all: BoolProperty(
        name=tr("Match All (Force)"),
        description=tr("Give every unmatched source group a target too: good "
                       "matches keep their 1:1 pairs, the rest take the closest "
                       "remaining target (empty groups go last).  Use this when "
                       "the source must end up with exactly the target's group "
                       "names, e.g. numeric bone ids 0..N"),
        default=False,
    )
    use_selected_only: BoolProperty(
        name=tr("Selected Vertices Only"),
        description=tr("Only consider selected vertices of the target object "
                       "(falls back to all vertices if nothing is selected)"),
        default=False,
    )
    min_weight: FloatProperty(
        name=tr("Min Weight"),
        description=tr("Weights at or below this are ignored in centroid mode"),
        default=0.01,
        min=0.0,
        max=1.0,
    )
    sample_limit: IntProperty(
        name=tr("Sample Limit"),
        description=tr("Maximum number of target vertices used for matching "
                       "(Transfer always uses every affected vertex)"),
        default=20000,
        min=100,
        soft_max=200000,
    )
    create_missing: BoolProperty(
        name=tr("Fill Missing Groups"),
        description=tr("After Apply: create empty vertex groups on the source "
                       "for target groups that received no weights"),
        default=True,
    )
    reorder_to_target: BoolProperty(
        name=tr("Match Target Order"),
        description=tr("After Apply: rebuild the source's vertex group list in "
                       "the same order as the target object (weights follow by "
                       "name, bindings are unaffected)"),
        default=True,
    )
    normalize_after: BoolProperty(
        name=tr("Normalize"),
        description=tr("After Transfer: rescale each affected vertex's total "
                       "weight to 1.0"),
        default=False,
    )

    items: CollectionProperty(type=WeightMatchItem)
    active_index: IntProperty(default=0)


classes = (WeightMatchItem, WeightMatchSettings)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.weight_match = PointerProperty(type=WeightMatchSettings)


def unregister():
    del bpy.types.Scene.weight_match
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
