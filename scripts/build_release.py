#!/usr/bin/env python3
"""Build the ecoflow-cloud.zip release asset.

HACS `zip_release` extracts the archive straight into
`custom_components/<domain>/` (see hacs/repositories/base.py:
`zip_file.extractall(self.content.path.local)`), so the component files must
sit at the ZIP ROOT -- NOT wrapped in a `custom_components/ecoflow_cloud/`
prefix. A prefixed zip installs nested
(`custom_components/ecoflow_cloud/custom_components/ecoflow_cloud/...`) and the
integration silently disappears from HA.

Usage:
    python3 scripts/build_release.py            # writes ecoflow-cloud.zip
    gh release create vX.Y.Z ecoflow-cloud.zip
"""
import json
import os
import zipfile

SRC = "custom_components/ecoflow_cloud"
OUT = "ecoflow-cloud.zip"


def main() -> None:
    manifest = json.load(open(os.path.join(SRC, "manifest.json"), encoding="utf-8"))
    print("manifest version:", manifest["version"])

    if os.path.exists(OUT):
        os.remove(OUT)

    count = 0
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(SRC):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for fn in sorted(filenames):
                if fn.endswith((".pyc", ".pyo")):
                    continue
                full = os.path.join(dirpath, fn)
                arc = os.path.relpath(full, SRC)  # strip the component prefix
                zf.write(full, arc)
                count += 1

    print("files zipped:", count)

    with zipfile.ZipFile(OUT) as zf:
        names = zf.namelist()
        assert "__init__.py" in names and "manifest.json" in names, (
            "zip root must contain the component files!"
        )
        assert not any(n.startswith("custom_components/") for n in names), (
            "no custom_components/ prefix allowed in the zip (HACS nesting bug)!"
        )

    print("ZIP ROOT-LEVEL OK:", OUT)


if __name__ == "__main__":
    main()
