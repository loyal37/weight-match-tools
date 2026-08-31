"""Weight Match Tools - match vertex groups between meshes by position.

Transfers character weights between models whose bone vertex-group names
(numbering) differ: the add-on finds which source group corresponds to which
target group by spatial overlap, shows an editable source = target mapping
table, then renames/merges the source groups or writes the weights straight
onto the target mesh.

Blender 4.2+ extension.  See README.md for the full workflow.
"""

if "bpy" in locals():
    import importlib
    importlib.reload(similarity)
    importlib.reload(matching)
    importlib.reload(properties)
    importlib.reload(operators)
    importlib.reload(ui)
    importlib.reload(translations)
else:
    from . import similarity, matching, properties, operators, ui, translations

import bpy

modules = (properties, operators, ui, translations)


def register():
    for m in modules:
        m.register()


def unregister():
    for m in reversed(modules):
        m.unregister()
