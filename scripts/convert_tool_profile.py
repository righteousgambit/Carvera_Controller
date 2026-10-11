"""Offline tool CAD conversion CLI; see converter module for explicit registration."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Read the module directly: CAD conversion environments do not need Kivy.
import importlib.util

_path = Path(__file__).resolve().parents[1] / "carveracontroller/addons/tool_visualization/converter.py"
_spec = importlib.util.spec_from_file_location("tool_converter", _path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
convert = _module.convert
source_triangles = _module.source_triangles
main = _module.main

if __name__ == "__main__":
    main()
