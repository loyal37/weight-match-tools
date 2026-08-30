# Weight Match Tools（Blender 权重改名匹配插件）

一个 Blender 4.2+（含 4.5 LTS）插件，解决**两个模型之间骨骼顶点组名称（编号）对不上**的权重搬运问题。

例如：想把 A 模型某个部件刷好的权重用到 B 模型的网格上，但 A 的顶点组叫 `1、2、3`，B 的叫 `head、body、foot`，直接转移权重会全部错位。本插件按**空间位置 / 权重分布**自动推断"源物体哪个顶点组 ≈ 目标物体哪个顶点组"，生成 `源名称 = 目标名称` 的映射表，然后：

- **改名/合并/补齐**源物体的顶点组为目标命名（之后可用你习惯的任何权重转移工具），或
- 用映射表**直接把权重转移到目标网格**（表面采样，支持不同拓扑/面数）。

## 安装

1. `编辑 (Edit) > 偏好设置 (Preferences) > 获取扩展 (Get Extensions)`
2. 右上角下拉箭头 > `从磁盘安装 (Install from Disk)`
3. 选择 `weight_match_tools.zip`（或直接选择 `weight_match_tools` 文件夹）

也可以用旧版方式：`编辑 > 偏好设置 > 插件 (Add-ons) > 从磁盘安装`，Blender 4.2+ 会自动识别扩展清单。

## 使用流程

1. 在 3D 视图侧边栏（N 面板）打开 **Weight Match** 标签页。
2. **Source** 选带权重的源模型（如 A 模型的部件），**Target** 选提供目标命名的模型（如绑好骨骼的 B 模型）。
3. 选择匹配模式，点 **Auto Match Groups**：

| 模式 | 原理 | 适用 |
|---|---|---|
| **Weight Field**（默认） | 把源顶点组的权重场采样到目标表面，与目标各顶点组的权重场做余弦相似度 | 最准确，推荐 |
| **Spatial Centroid** | 按每个顶点组权重的加权中心（世界坐标）距离匹配 | 快；权重场接近全 0/1 的均匀组 |
| **Name Only** | 名字清洗后（忽略大小写/分隔符）直接同名匹配 | 名字只差前后缀/大小写 |

4. 检查映射表：每行 `源组 → 目标组 + 相似度%`，可手动改下拉框、勾掉不需要的行；筛选框可按名字过滤。
5. 二选一：
   - **Apply to Source (Rename/Merge)**：把源物体顶点组改名为目标命名；重名时权重**相加合并**（上限 1.0）；开启 *Fill Missing Groups* 会为没匹配到的目标组在源物体上创建**空顶点组**（补齐骨骼命名，避免绑定时缺组）。之后你可以用 Blender 自带的数据传输等工具转移权重。
   - **Transfer Weights to Target**：直接把源权重按映射表采样写到目标网格的顶点组上（自动创建缺失的目标组）。开启 *Normalize* 可把受影响顶点的总权重归一化到 1。

### 局部（部件）工作流

只给 B 模型的某个部位刷权重：在编辑模式下选中 B 模型上该部位的顶点，勾选 **Selected Vertices Only**——匹配和转移都只作用于选中顶点（没有选中顶点时自动退回全部）。

### 常用选项

- **Min Similarity**：低于该相似度的配对不匹配（留空待手动指定）。
- **Lock Same Names**：两边同名的组直接锁定配对，不参与自动分配。
- **Allow Many-to-One**：允许多个源组映射到同一个目标组（Apply 时合并权重），适合源模型骨骼切分更细的情况。
- **Sample Limit**：匹配时最多采样多少目标顶点（加速大网格；Transfer 不受影响）。

## 命令行 / 脚本

操作符可在脚本中直接调用：

```python
import bpy
s = bpy.context.scene.weight_match
s.source_object = bpy.data.objects["A_body"]
s.target_object = bpy.data.objects["B_rigged"]
s.match_mode = 'WEIGHT'          # WEIGHT / CENTROID / NAME
bpy.ops.weight_match.auto_match()
bpy.ops.weight_match.apply_rename()     # 或 transfer_weights()
```

映射表也可以导出 CSV：`source,target,similarity,enabled`。

## 注意事项

- 匹配与采样都在两物体各自的**局部坐标**下进行：物体摆在场景哪个位置都不影响结果，只要求两个网格在各自的建模空间里形状对位（同一基础模型换绑/改名的典型情况就是如此）。若两边局部空间不一致（例如一个被旋转过 90°），先调整物体变换使其对位。
- Apply 改名会改动源物体顶点组名：如果源物体还绑着自己的骨架，其变形会暂时失效——这正是目的（改为对应目标骨架的骨骼名）。
- 大网格（>10 万面）匹配约需数秒（受 Sample Limit 限制）；Transfer 与顶点数×组数成正比，可配合 *Selected Vertices Only* 只处理局部。
- 多个组的权重场都很均匀（几乎全 1）时，Weight Field 模式的相似度可能都接近 1，此时建议改用 Spatial Centroid 模式或手动微调映射表。

## 开发与测试

```bash
# 纯算法单元测试（系统 Python，需 numpy）
python tests/test_similarity.py

# Blender 无头集成测试
"D:\blender4,5\blender.exe" --background --factory-startup --python tests/test_headless.py

# 打包安装 zip
python make_zip.py
```

## 目录结构

```
weight_match_tools/
├── blender_manifest.toml   # 扩展清单
├── __init__.py             # 注册入口
├── similarity.py           # 纯算法：余弦相似度/贪心分配/名字清洗（无 Blender 依赖）
├── matching.py             # 权重场采样、BVH 最近面、质心匹配
├── properties.py           # 场景属性与映射表数据
├── operators.py            # 自动匹配 / 应用改名 / 权重转移 / 导出
└── ui.py                   # N 面板与映射表 UIList
```

## 许可

GPL-3.0-or-later（Blender 扩展平台要求）。
