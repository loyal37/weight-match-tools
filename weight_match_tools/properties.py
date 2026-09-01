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

from .i18n import register_rna_class, tr, unregister_rna_class

# Sentinel target value meaning "leave the source group's name unchanged".
KEEP = "__KEEP__"

# Blender keeps pointers to strings returned by dynamic EnumProperty callbacks.
# Those strings therefore need to outlive the temporary list returned by the
# callback; otherwise entries (especially non-ASCII names) can turn into
# garbage and a later assignment is rejected as "enum value not found".
_ENUM_STRINGS = {KEEP: KEEP}
_TARGET_GROUP_ITEMS = []
_TARGET_GROUP_KEY = None


def _poll_mesh_object(self, obj):
    return obj.type == 'MESH'


def _stable_enum_string(value):
    value = str(value)
    return _ENUM_STRINGS.setdefault(value, value)


def _target_group_items(self, context):
    """Dynamic enum listing the target object's vertex groups."""
    global _TARGET_GROUP_ITEMS, _TARGET_GROUP_KEY

    target = None
    try:
        settings = context.scene.weight_match
        target = settings.target_object
    except Exception:
        pass

    names = tuple(vg.name for vg in target.vertex_groups) if target else ()
    target_id = target.as_pointer() if target else 0
    key = (target_id, names, tr("(keep name)"),
           tr("Leave this source group's name unchanged"))
    if key != _TARGET_GROUP_KEY:
        items = [(
            KEEP,
            _stable_enum_string(key[2]),
            _stable_enum_string(key[3]),
        )]
        for name in names:
            stable = _stable_enum_string(name)
            items.append((stable, stable, ""))
        _TARGET_GROUP_ITEMS = items
        _TARGET_GROUP_KEY = key
    return _TARGET_GROUP_ITEMS


def _update_target_enum(self, context):
    self.target_name = "" if self.target_enum == KEEP else self.target_enum


class WeightMatchItem(bpy.types.PropertyGroup):
    """One row of the source -> target mapping table."""

    source_name: StringProperty(name=tr("Source Group"))
    source_side: StringProperty(
        name=tr("Source Side"),
        description=tr("Internal spatial half used when a bilateral source "
                       "group is split automatically"),
        default="",
    )
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
             tr("Sample the target weight fields onto the source surface "
                "and compare them with each weighted source group "
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
    allow_merge: BoolProperty(
        name=tr("Allow Many-to-One"),
        description=tr("Let several source groups match the same target group "
                       "(their weights are merged on Apply)"),
        default=False,
    )
    force_match_all: BoolProperty(
        name=tr("Match All (Force)"),
        description=tr("Give every unmatched weighted source group a target: good "
                       "matches keep their 1:1 pairs, the rest take the closest "
                       "remaining weighted deform group. Empty groups do not "
                       "participate; Apply rebuilds them from the target"),
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
        description=tr("Maximum number of surface vertices used for matching "
                       "(Transfer always uses every affected vertex)"),
        default=20000,
        min=100,
        soft_max=200000,
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
        register_rna_class(cls)
    if hasattr(bpy.types.Scene, "weight_match"):
        del bpy.types.Scene.weight_match
    bpy.types.Scene.weight_match = PointerProperty(type=WeightMatchSettings)


def unregister():
    if hasattr(bpy.types.Scene, "weight_match"):
        del bpy.types.Scene.weight_match
    for cls in reversed(classes):
        unregister_rna_class(cls)
