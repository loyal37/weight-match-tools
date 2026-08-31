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

ZH = {
    # panel / tab
    "Weight Match": "权重匹配",
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
    "Sample each source group's weights onto the target surface and "
    "compare against the target groups' weight fields "
    "(most accurate, recommended)":
        "把源顶点组的权重采样到目标表面，与目标各顶点组的权重场对比"
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
    "Lock Same Names": "锁定同名组",
    "Groups whose names are identical on both sides are "
    "matched first and excluded from automatic assignment":
        "两边同名的顶点组直接锁定配对，不参与自动分配",
    "Allow Many-to-One": "允许多对一",
    "Let several source groups match the same target group "
    "(their weights are merged on Apply)":
        "允许多个源顶点组匹配到同一个目标顶点组"
        "（应用/转移时权重合并），适合源模型骨骼划分更细的情况",
    "Match All (Force)": "全量匹配（强制）",
    "Give every unmatched source group a target too: good "
    "matches keep their 1:1 pairs, the rest take the closest "
    "remaining target (empty groups go last).  Use this when "
    "the source must end up with exactly the target's group "
    "names, e.g. numeric bone ids 0..N":
        "让每个未匹配的源组也获得目标：高质量配对保持 1:1 不变，"
        "其余按相似度认领剩余目标组（空组排最后）。"
        "当源物体必须恰好使用目标的全部组名时勾选，"
        "例如 0~N 的数字骨骼编号",
    "Selected Vertices Only": "仅用选中顶点",
    "Only consider selected vertices of the target object "
    "(falls back to all vertices if nothing is selected)":
        "只考虑目标物体上选中的顶点（没有选中时自动退回全部顶点）",
    "Min Weight": "最小权重",
    "Weights at or below this are ignored in centroid mode":
        "质心模式下忽略小于等于该值的权重",
    "Sample Limit": "采样上限",
    "Maximum number of target vertices used for matching "
    "(Transfer always uses every affected vertex)":
        "匹配时最多采样多少目标顶点（权重转移始终处理全部受影响顶点）",

    # settings: apply / transfer options
    "Fill Missing Groups": "补齐缺失组",
    "After Apply: create empty vertex groups on the source "
    "for target groups that received no weights":
        "应用后：为没有获得权重的目标组在源物体上创建空顶点组",
    "Match Target Order": "按目标顺序排列",
    "After Apply: rebuild the source's vertex group list in "
    "the same order as the target object (weights follow by "
    "name, bindings are unaffected)":
        "应用后：把源物体的顶点组列表按目标物体的顺序重建"
        "（权重按名字跟随，骨架绑定不受影响）",
    "Normalize": "归一化",
    "After Transfer: rescale each affected vertex's total "
    "weight to 1.0":
        "转移后：把受影响顶点的总权重重新缩放到 1.0",

    # mapping table rows
    "Source Group": "源顶点组",
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
    "match_mode", "similarity_threshold", "prefer_same_name", "allow_merge",
    "force_match_all", "use_selected_only", "min_weight", "sample_limit",
    "create_missing", "reorder_to_target", "normalize_after", "active_index",
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
            "simple": {f: getattr(s, f) for f in _SNAPSHOT_SIMPLE},
            "items": [(it.source_name, it.target_name, it.similarity,
                       it.enabled) for it in s.items],
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
            setattr(s, f, v)
        s.items.clear()
        for src, tgt, sim, enabled in d["items"]:
            it = s.items.add()
            it.source_name = src
            it.target_enum = tgt if tgt else KEEP
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
    for module in (ui, operators, properties):
        for cls in reversed(getattr(module, "classes", ())):
            bpy.utils.unregister_class(cls)
    if hasattr(bpy.types.Scene, "weight_match"):
        del bpy.types.Scene.weight_match

    importlib.reload(properties)
    importlib.reload(operators)
    importlib.reload(ui)

    for module in (properties, operators, ui):
        for cls in module.classes:
            bpy.utils.register_class(cls)
    bpy.types.Scene.weight_match = PointerProperty(
        type=properties.WeightMatchSettings)
    _restore(snap)


classes = (WeightMatchLangPrefs,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.wmt_lang = PointerProperty(
        type=WeightMatchLangPrefs)


def unregister():
    del bpy.types.WindowManager.wmt_lang
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
