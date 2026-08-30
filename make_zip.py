"""Package the add-on folder into an installable extension zip.

Run:  py make_zip.py   ->  dist/weight_match_tools-<version>.zip
"""

import os
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "weight_match_tools")


def manifest_version():
    with open(os.path.join(SRC, "blender_manifest.toml"), encoding="utf-8") as f:
        for line in f:
            if line.startswith("version"):
                return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("version not found in blender_manifest.toml")


def main():
    version = manifest_version()
    out_dir = os.path.join(ROOT, "dist")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"weight_match_tools-{version}.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for base, dirs, files in os.walk(SRC):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for name in files:
                if name.endswith(".pyc"):
                    continue
                path = os.path.join(base, name)
                z.write(path, os.path.relpath(path, ROOT))
    print("wrote", out)


if __name__ == "__main__":
    main()
