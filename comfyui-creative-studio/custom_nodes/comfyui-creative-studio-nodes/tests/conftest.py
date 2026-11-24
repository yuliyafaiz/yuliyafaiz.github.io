"""Test setup: make the package importable and provide a stub ``folder_paths``.

Inside ComfyUI, ``folder_paths`` is the real module; here we point it at a tmp dir.
"""
import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest

PKG_DIR = Path(__file__).resolve().parents[1]


def _load_package():
    name = "cs_test_pkg"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, PKG_DIR / "__init__.py",
                                                  submodule_search_locations=[str(PKG_DIR)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def pkg():
    return _load_package()


@pytest.fixture
def core(pkg):
    return sys.modules["cs_test_pkg.cs_nodes.core"]


@pytest.fixture
def comfy_dirs(tmp_path, monkeypatch):
    inp, out, models = tmp_path / "input", tmp_path / "output", tmp_path / "models"
    for d in (inp, out, models / "checkpoints"):
        d.mkdir(parents=True)
    fp = types.ModuleType("folder_paths")
    fp.get_input_directory = lambda: str(inp)
    fp.get_output_directory = lambda: str(out)
    fp.get_user_directory = lambda: str(tmp_path / "user")

    def get_full_path(folder, name):
        p = models / folder / name
        return str(p) if p.exists() else None

    def get_save_image_path(prefix, output_dir, w=0, h=0):
        full = os.path.join(output_dir, os.path.dirname(prefix))
        os.makedirs(full, exist_ok=True)
        return full, os.path.basename(prefix), 1, os.path.dirname(prefix), prefix

    fp.get_full_path = get_full_path
    fp.get_save_image_path = get_save_image_path
    monkeypatch.setitem(sys.modules, "folder_paths", fp)
    return types.SimpleNamespace(input=inp, output=out, models=models)
