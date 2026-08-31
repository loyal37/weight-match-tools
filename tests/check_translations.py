"""Check that every tr() call in the UI code has a zh_CN entry (and no orphans).

Run:  py tests/check_translations.py
"""

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# i18n imports bpy (unavailable here), so parse the ZH dict out with ast -
# implicit string concatenation is merged at parse time, so literal_eval works.
with open(os.path.join(ROOT, "weight_match_tools", "i18n.py"),
          encoding="utf-8") as f:
    tree = ast.parse(f.read())
ZH = None
for node in tree.body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) \
            and node.targets[0].id == "ZH":
        ZH = ast.literal_eval(node.value)
if ZH is None:
    sys.exit("FAIL - ZH dict not found in i18n.py")

CODE_FILES = ["properties.py", "operators.py", "ui.py"]


def const_text(node):
    """Value of a string constant or implicit concat of such, else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = const_text(node.left), const_text(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def tr_args(tree):
    """Collect the string arguments of tr(...) calls."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "tr":
            for arg in node.args:
                text = const_text(arg)
                if text is not None and len(text) >= 3 and text.isascii():
                    yield text


used = set()
failures = []
for fname in CODE_FILES:
    path = os.path.join(ROOT, "weight_match_tools", fname)
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for text in tr_args(tree):
        used.add(text)
        if text not in ZH:
            failures.append(f"{fname}: no zh entry for {text!r}")

for key in ZH:
    if key not in used:
        failures.append(f"zh entry never used in code: {key!r}")

if failures:
    for f in failures:
        print("FAIL -", f)
    sys.exit(1)
print(f"ALL {len(ZH)} zh ENTRIES MATCH tr() CALLS ({len(used)} strings)")
