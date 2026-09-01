"""Sidebar panel and mapping-table UI list."""

import bpy

from .i18n import register_rna_class, tr, unregister_rna_class


class WEIGHTMATCH_UL_mapping(bpy.types.UIList):
    """The source -> target mapping table."""

    def draw_item(self, context, layout, _data, item, _icon, _active_data,
                  _active_propname, _index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.prop(item, "enabled", text="")
            side = f" [{'+X' if item.source_side == 'POS' else '-X'}]" \
                if item.source_side else ""
            row.label(text=item.source_name + side, icon='GROUP_VERTEX')
            row.label(text="", icon='TRIA_RIGHT')
            row.prop(item, "target_enum", text="")
            row.label(text=f"{item.similarity * 100:.0f}%")
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text="", icon='GROUP_VERTEX')


class WEIGHTMATCH_PT_main(bpy.types.Panel):
    # The add-on identity stays English.  The language switch only rebuilds
    # labels and descriptions inside this panel.
    bl_label = "Weight Match"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Weight Match"

    def draw(self, context):
        s = context.scene.weight_match
        layout = self.layout

        row = layout.row(align=True)
        row.label(text="Language / 语言")
        row.prop(context.window_manager.wmt_lang, "language", text="")

        col = layout.column(align=True)
        col.prop(s, "source_object")
        col.prop(s, "target_object")

        box = layout.box()
        box.label(text=tr("Matching"), icon='MOD_DATA_TRANSFER')
        col = box.column(align=True)
        col.prop(s, "match_mode", text="")
        if s.match_mode != 'NAME':
            col.prop(s, "similarity_threshold")
        if s.match_mode == 'CENTROID':
            col.prop(s, "min_weight")
        if s.match_mode == 'WEIGHT':
            col.prop(s, "sample_limit")
        col.prop(s, "allow_merge")
        col.prop(s, "force_match_all")
        col.prop(s, "use_selected_only")
        col.operator("weight_match.auto_match", icon='SNAP_ON')
        col.operator("weight_match.batch_match", icon='GROUP_VERTEX')

        box = layout.box()
        matched = sum(1 for it in s.items if it.target_name)
        head = box.row(align=True)
        head.label(text=tr("Mapping"), icon='GROUP_VERTEX')
        head.label(text=f"({matched}/{len(s.items)})")
        box.template_list("WEIGHTMATCH_UL_mapping", "", s, "items",
                          s, "active_index",
                          rows=6 if s.items else 1)

        col = box.column(align=True)
        col.operator("weight_match.apply_rename", icon='CHECKMARK')
        col.prop(s, "normalize_after")
        col.operator("weight_match.transfer_weights", icon='MOD_VERTEX_WEIGHT')

        row = col.row(align=True)
        row.operator("weight_match.export_csv", icon='EXPORT')
        row.operator("weight_match.clear_mapping", icon='TRASH')


classes = (
    WEIGHTMATCH_UL_mapping,
    WEIGHTMATCH_PT_main,
)


def register():
    for cls in classes:
        register_rna_class(cls)


def unregister():
    for cls in reversed(classes):
        unregister_rna_class(cls)
