"""Shared configuration and trusted runtime fixtures for development checks."""
from importlib.machinery import SourceFileLoader
import importlib.util
from pathlib import Path
import sys
import types
import typing
from unittest.mock import patch

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPOSITORY_ROOT
EVALUATION_TOOLS = REPOSITORY_ROOT / "scripts/devtools/report_evaluation"


def load_runtime(source_root):
    import pandas as pd

    report = source_root / "skills/report-codegen"
    modules = {name: types.ModuleType(name) for name in ("common_utils", "common_utils.all_modules")}
    modules["common_utils.all_modules"].pd = pd
    modules["common_utils.all_modules"].Dict = typing.Dict
    modules["common_utils.all_modules"].logger = types.SimpleNamespace(info=lambda *args, **kwargs: None)
    if (report / "scripts/declared_constraints.py").is_file():
        import declared_constraints
        modules["data_utils"] = types.ModuleType("data_utils")
        modules["data_utils"].__path__ = []
        modules["data_utils.declared_constraints"] = declared_constraints
    loader = SourceFileLoader("pipeline_test_runtime", str(report / "assets/minimal_report_project/data_utils/contract_runtime.py.template"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        loader.exec_module(module)
    return module
