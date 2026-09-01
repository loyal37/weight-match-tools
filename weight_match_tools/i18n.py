"""Add-on-local bilingual support (zh_CN default) with a language switch.

Blender's own translation system follows the global interface language and
cannot be overridden per add-on, so labels are resolved through tr() at
class-creation time instead.  Switching the language re-registers the UI
classes; the mapping table and settings are snapshotted and restored across
the switch.

The language choice itself lives on the WindowManager (not reloaded), so it
persists for the session; it defaults to Chinese.
"""

import bpy
from bpy.props import EnumProperty, PointerProperty

# Preserved across module reloads (importlib.reload keeps the namespace).
LANG = globals().get("LANG", "zh_CN")

# Keep the exact Python class objects handed to Blender.  Some RNA types (in
# particular operators) cannot reliably be recovered through bpy.types by
# their Python class name, and module reloads replace the module's class
# objects.  The registry itself survives importlib.reload().
_REGISTERED_CLASSES = globals().get("_REGISTERED_CLASSES", {})

ZH = {
    # panel / tab
    "Matching": "匹配设置",
    "Mapping": "映射表",

    # settings: objects
    "Source": "源物体",
    "Target": "目标物体",
    "Mesh whose vertex groups will be renamed/merged, "
    "and whose weights are read from":
        "要被改名/合并、并从中读取权重的网格",
    "Mesh providing the destination naming "
    "(usually the rigged model you want weights to end up on)":
        "提供目标命名的网格（通常是想把权重最终放上去的绑定模型）",

    # settings: matching options
    "Match Mode": "匹配模式",
    "Weight Field": "权重场",
    "Sample the target weight fields onto the source surface "
    "and compare them with each weighted source group "
    "(most accurate, recommended)":
        "把目标权重场采样到源物体表面，与源侧各非空权重组对比"
        "（最准确，推荐）",
    "Spatial Centroid": "空间质心",
    "Match each group's weighted average position "
    "(fast; good when weight fields are close to uniform)":
        "按每个顶点组的加权平均位置匹配（快速；适合权重接近均匀的组）",
    "Name Only": "仅按名称",
    "Match names after cleanup (case/punctuation ignored); "
    "no spatial test":
        "清洗名字后直接同名匹配（忽略大小写/分隔符）；不做空间检测",
    "Min Similarity": "最小相似度",
    "Pairs below this similarity are left unmatched":
        "低于该相似度的配对不匹配（留空待手动指定）",
    "Allow Many-to-One": "允许多对一",
    "Let several source groups match the same target group "
    "(their weights are merged on Apply)":
        "允许多个源顶点组匹配到同一个目标顶点组"
        "（应用/转移时权重合并），适合源模型骨骼划分更细的情况",
    "Match All (Force)": "全量匹配（强制）",
    "Give every unmatched weighted source group a target: good "
    "matches keep their 1:1 pairs, the rest take the closest "
    "remaining weighted deform group. Empty groups do not "
    "participate; Apply rebuilds them from the target":
        "让每个未匹配的非空源组也获得目标：高质量配对保持 1:1 不变，"
        "其余按相似度认领非空骨骼目标组。空组不参与匹配，"
        "应用时按目标模板重新补齐",
    "Selected Vertices Only": "仅用选中顶点",
    "Only consider selected vertices of the target object "
    "(falls back to all vertices if nothing is selected)":
        "只考虑目标物体上选中的顶点（没有选中时自动退回全部顶点）",
    "Min Weight": "最小权重",
    "Weights at or below this are ignored in centroid mode":
        "质心模式下忽略小于等于该值的权重",
    "Sample Limit": "采样上限",
    "Maximum number of surface vertices used for matching "
    "(Transfer always uses every affected vertex)":
        "匹配时最多采样多少表面顶点（权重转移始终处理全部受影响顶点）",

    # settings: apply / transfer options
    "Normalize": "归一化",
    "After Transfer: rescale each affected vertex's total "
    "weight to 1.0":
        "转移后：把受影响顶点的总权重重新缩放到 1.0",

    # mapping table rows
    "Source Group": "源顶点组",
    "Source Side": "源空间侧",
    "Internal spatial half used when a bilateral source "
    "group is split automatically":
        "双侧源顶点组自动拆分时使用的内部空间半侧",
    "Target Group": "目标顶点组",
    "Which target vertex group this source group becomes":
        "这个源顶点组将变成哪个目标顶点组",
    "Similarity": "相似度",
    "How well the two weight fields agree (1 = identical)":
        "两个权重场的吻合程度（1 = 完全一致）",
    "Apply": "应用",
    "Include this row when applying or transferring":
        "应用/转移时包含这一行",
    "(keep name)": "（保留原名）",
    "Leave this source group's name unchanged":
        "不改变该源顶点组的名称",

    # operators
    "Auto Match Groups": "自动匹配顶点组",
    "Guess which source vertex group corresponds to which "
    "target vertex group and fill the mapping table":
        "推断源物体哪个顶点组对应目标物体哪个顶点组，并生成映射表",
    "Batch Match Selected": "批量匹配选中物体",
    "Run Auto Match + Apply on every selected mesh (except "
    "the target) against the target object, using the "
    "current matching settings":
        "对除目标物体外的所有选中网格，按当前匹配设置"
        "依次执行自动匹配+应用（改名/合并/补齐/排序）",
    "Apply to Source (Rename/Merge)": "应用到源（改名/合并）",
    "Rename the source object's vertex groups to the matched "
    "target names, merging weights where names collide, and "
    "create empty groups for missing target groups":
        "把源物体的顶点组改名为匹配到的目标名，重名时合并权重，"
        "并为缺失的目标组创建空组",
    "Transfer Weights to Target": "转移权重到目标",
    "Write the source groups' weights onto the target mesh "
    "using the mapping table (surface sampling, so it works "
    "across different topology)":
        "用映射表把源顶点组的权重写到目标网格上"
        "（表面采样，支持不同拓扑）",
    "Export Mapping (CSV)": "导出映射（CSV）",
    "Save the current mapping table as a CSV file":
        "把当前映射表保存为 CSV 文件",
    "Clear Mapping": "清空映射",
    "Empty the mapping table": "清空映射表",
    "File Path": "文件路径",
    "Where to save the CSV": "CSV 保存位置",
}

DICTS = {"zh_CN": ZH, "en_US": {}}


def tr(text):
    if LANG == "zh_CN":
        return ZH.get(text, text)
    return text


def register_rna_class(cls):
    """Register ``cls``, recovering an orphan with the same RNA name."""
    key = cls.__name__
    previous = _REGISTERED_CLASSES.pop(key, None)
    current = getattr(bpy.types, key, None)
    seen = set()
    for candidate in (previous, cls, current):
        if candidate is None or id(candidate) in seen:
            continue
        seen.add(id(candidate))
        if not hasattr(candidate, "bl_rna"):
            continue
        try:
            bpy.utils.unregister_class(candidate)
        except RuntimeError as exc:
            if "missing bl_rna attribute" not in str(exc):
                raise
    bpy.utils.register_class(cls)
    _REGISTERED_CLASSES[key] = cls


def unregister_rna_class(cls):
    """Unregister the class Blender actually owns, not a stale reload copy."""
    key = cls.__name__
    previous = _REGISTERED_CLASSES.pop(key, None)
    current = getattr(bpy.types, key, None)
    seen = set()
    for candidate in (previous, cls, current):
        if candidate is None or id(candidate) in seen:
            continue
        seen.add(id(candidate))
        if not hasattr(candidate, "bl_rna"):
            continue
        try:
            bpy.utils.unregister_class(candidate)
        except RuntimeError as exc:
            # A failed hot reload may leave a Python class name around after
            # its RNA registration is already gone.
            if "missing bl_rna attribute" not in str(exc):
                raise


# ---------------------------------------------------------------------------
# language switching


class WeightMatchLangPrefs(bpy.types.PropertyGroup):
    language: EnumProperty(
        name="Language / 语言",
        items=(
            ('zh_CN', "中文", ""),
            ('en_US', "English", ""),
        ),
        default='zh_CN',
        update=lambda self, context: _on_lang_update(self, context),
    )


def _on_lang_update(self, context):
    global LANG
    LANG = self.language
    # Defer the class rebuild so it does not run inside the UI redraw that
    # triggered the change.
    if not bpy.app.timers.is_registered(_apply_deferred):
        bpy.app.timers.register(_apply_deferred)


def _apply_deferred():
    apply_language(LANG)


# fields carried across a language switch
_SNAPSHOT_SIMPLE = (
    "match_mode", "similarity_threshold", "allow_merge", "force_match_all",
    "use_selected_only", "min_weight", "sample_limit",
    "normalize_after", "active_index",
)


def _snapshot():
    data = {}
    for scene in bpy.data.scenes:
        s = getattr(scene, "weight_match", None)
        if s is None:
            continue
        data[scene.name] = {
            "source": s.source_object.name if s.source_object else "",
            "target": s.target_object.name if s.target_object else "",
            "simple": {f: getattr(s, f) for f in _SNAPSHOT_SIMPLE
                       if hasattr(s, f)},
            "items": [(it.source_name, it.source_side, it.target_name,
                       it.similarity, it.enabled) for it in s.items],
        }
    return data


def _restore(data):
    from .properties import KEEP
    for scene in bpy.data.scenes:
        d = data.get(scene.name)
        if not d:
            continue
        s = scene.weight_match
        s.source_object = bpy.data.objects.get(d["source"]) if d["source"] else None
        s.target_object = bpy.data.objects.get(d["target"]) if d["target"] else None
        for f, v in d["simple"].items():
            if hasattr(s, f):
                setattr(s, f, v)
        valid_targets = ({vg.name for vg in s.target_object.vertex_groups}
                         if s.target_object else set())
        s.items.clear()
        for src, side, tgt, sim, enabled in d["items"]:
            it = s.items.add()
            it.source_name = src
            it.source_side = side
            it.target_enum = tgt if tgt in valid_targets else KEEP
            it.similarity = sim
            it.enabled = enabled
        s.active_index = d["simple"]["active_index"]


def apply_language(lang):
    """Rebuild all UI classes so RNA labels use the given language."""
    global LANG
    LANG = lang
    import importlib
    from . import properties, operators, ui

    snap = _snapshot()
    # Remove the RNA pointer before unregistering its PropertyGroup types.
    # Doing this in the opposite order can leave a half-unregistered panel if
    # Blender rejects the class teardown during the deferred UI callback.
    if hasattr(bpy.types.Scene, "weight_match"):
        del bpy.types.Scene.weight_match
    for module in (ui, operators, properties):
        for cls in reversed(getattr(module, "classes", ())):
            unregister_rna_class(cls)

    importlib.reload(properties)
    importlib.reload(operators)
    importlib.reload(ui)

    for module in (properties, operators, ui):
        for cls in module.classes:
            register_rna_class(cls)
    bpy.types.Scene.weight_match = PointerProperty(
        type=properties.WeightMatchSettings)
    _restore(snap)


classes = (WeightMatchLangPrefs,)


def register():
    for cls in classes:
        register_rna_class(cls)
    if hasattr(bpy.types.WindowManager, "wmt_lang"):
        del bpy.types.WindowManager.wmt_lang
    bpy.types.WindowManager.wmt_lang = PointerProperty(
        type=WeightMatchLangPrefs)


def unregister():
    if hasattr(bpy.types.WindowManager, "wmt_lang"):
        del bpy.types.WindowManager.wmt_lang
    for cls in reversed(classes):
        unregister_rna_class(cls)
