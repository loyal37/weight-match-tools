"""Check that every UI string in the code has a zh_CN translation entry.

Only inspects the translatable slots: name=/description= keyword arguments
and bl_label/bl_description/bl_category assignments (including implicit
string concatenation).

Run:  py tests/check_translations.py
"""

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "weight_match_tools"))

from translations import TRANSLATIONS  # noqa: E402

CODE_FILES = ["properties.py", "operators.py", "ui.py"]
UI_KWARGS = {"name", "description"}


def const_text(node):
    """Value of a string constant or implicit concat of such, else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = const_text(node.left), const_text(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def ui_strings(tree, tuple_items):
    for node in ast.walk(tree):
        # keyword args: name="...", description="...", text="..."
        if isinstance(node, ast.keyword) and node.arg in UI_KWARGS | {"text"}:
            text = const_text(node.value)
            if text is not None and len(text) >= 3:
                yield text
        # assignments: bl_label = "..." / bl_description = "..." / bl_category = "..."
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id in {"bl_label", "bl_description", "bl_category"}:
            text = const_text(node.value)
            if text is not None:
                yield text
        # enum item tuples: (identifier, name, description) — properties.py only
        if tuple_items and isinstance(node, (ast.Tuple, ast.List)):
            for elt in node.elts:
                text = const_text(elt)
                if text is not None and len(text) >= 3 and text.isascii() \
                        and not text.isupper():  # skip enum identifiers
                    yield text


failures = []
keys = TRANSLATIONS["*"]
code_strings = set()

for fname in CODE_FILES:
    path = os.path.join(ROOT, "weight_match_tools", fname)
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for text in ui_strings(tree, tuple_items=(fname == "properties.py")):
        code_strings.add(text)
        if text not in keys:
            failures.append(f"{fname}: missing translation for {text!r}")

for key in keys:
    if key not in code_strings:
        failures.append(f"dict key not found in any UI slot: {key!r}")

if failures:
    for f in failures:
        print("FAIL -", f)
    sys.exit(1)
print(f"ALL {len(keys)} TRANSLATION KEYS MATCH THE UI STRINGS")
