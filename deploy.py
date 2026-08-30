"""Deploy the add-on straight into the local Blender user config.

Copies the weight_match_tools folder into the Blender 4.x user extensions
directory so it is active after a Blender restart (or F3 > Reload Scripts).

Run:  py deploy.py
"""

import os
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "weight_match_tools")

BLENDER_USER_CONFIG = os.path.expandvars(
    r"%APPDATA%\Blender Foundation\Blender\4.5")
TARGETS = [
    os.path.join(BLENDER_USER_CONFIG, "extensions", "user_default",
                 "weight_match_tools"),
]


def deploy(src, dst):
    if os.path.exists(dst):
        try:
            shutil.rmtree(dst)
        except PermissionError:
            print(f"  !! {dst} is locked (Blender running?) - copying over instead")
            shutil.rmtree(os.path.join(dst, "__pycache__"), ignore_errors=True)
            shutil.copytree(src, dst, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            return
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    print("deployed ->", dst)


def main():
    for dst in TARGETS:
        deploy(SRC, dst)
        with open(os.path.join(dst, "blender_manifest.toml"), encoding="utf-8") as f:
            for line in f:
                if line.startswith("version"):
                    print("  ", dst, line.strip())
                    break


if __name__ == "__main__":
    main()
