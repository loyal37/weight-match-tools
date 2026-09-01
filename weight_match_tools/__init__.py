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
    # Reload i18n too so hot-deployed schema changes do not leave stale
    # snapshot fields or class helpers in memory.  Registration is recovered
    # safely by the RNA helpers in that module.
    importlib.reload(i18n)
    importlib.reload(similarity)
    importlib.reload(matching)
    importlib.reload(properties)
    importlib.reload(operators)
    importlib.reload(ui)
else:
    from . import i18n, similarity, matching, properties, operators, ui

import bpy

modules = (i18n, properties, operators, ui)


def register():
    for m in modules:
        m.register()


def unregister():
    for m in reversed(modules):
        m.unregister()
