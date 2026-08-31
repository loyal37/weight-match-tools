"""Simplified Chinese UI translations.

Uses Blender's translation dictionary, so the add-on shows English when the
interface language is English and Chinese when it is set to zh_* (with
Preferences > Interface > Translation > Interface enabled).
"""

TRANSLATIONS = {
    "*": {
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
}


def register():
    import bpy
    bpy.app.translations.register(__name__, TRANSLATIONS)


def unregister():
    import bpy
    bpy.app.translations.unregister(__name__)
