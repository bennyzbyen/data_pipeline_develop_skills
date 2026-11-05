"""Offline regressions for source-based operator refactors and private ZIP delivery."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

from pipeline_test_support import SOURCE_ROOT

SKILLS = SOURCE_ROOT / "skills"
GUIDE = SKILLS / "pipeline-forge-guide" / "scripts"
for directory in (GUIDE, SKILLS / "report-codegen/scripts", SKILLS / "data-sync-codegen/scripts"):
    sys.path.insert(0, str(directory))

from scaffold_report_project import scaffold
from verify_cot_manifest_semantics_regression import facts_for, generate
from verify_generated_safety import verify as verify_safety
from verify_generic_report_runtime_semantics import build_plan
from verify_operator_package import verify as verify_zip


class OperatorRefactors(unittest.TestCase):
    def test_native_unit_bypasses_scaffolding_even_with_force(self):
        facts = facts_for("fixture_p", ["period", "code", "inksaa_last_modified_timestamp"])
        unit = {"code_unit_id": "sync", "codegen_route": "data-sync-codegen",
                "implementation_contract": {"mode": "preserve_existing"}}
        facts.update(code_unit_plan={"status": "confirmed", "confirmed_count": 1},
                     code_units=[unit], waterlines=[])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            with self.assertRaisesRegex(ValueError, "preserve_existing"):
                generate(facts, project)
            self.assertFalse(project.exists())
            dispatch = subprocess.check_output(
                [sys.executable, str(GUIDE / "build_code_unit_dispatch.py"),
                 "--facts", str(root / "project_facts.json"), "--output-root", str(root)], text=True)
            row = json.loads(dispatch)["code_units"][0]
            self.assertEqual(row["implementation_mode"], "preserve_existing")
            self.assertEqual(row["commands"], {})

    def test_both_scaffolders_preserve_modified_connection_files_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = facts_for("fixture_p", ["period", "code", "inksaa_last_modified_timestamp"])
            plan = root / "plan.json"
            plan.write_text(json.dumps(build_plan("standard_report")), encoding="utf-8")
            for name, relative, build in [
                ("sync", "cot_config/plugin_config.py", lambda path: generate(facts, path)),
                ("report", "params_configs/db_config.py", lambda path: scaffold(plan, path)),
            ]:
                with self.subTest(name=name):
                    target = root / name
                    build(target)
                    build(target)  # A pristine bundled project still supports regeneration.
                    config = target / relative
                    config.write_bytes(b"app_key = 'fixture_private_provider'\n")
                    entry = target / "plugin_main.py"
                    entry.write_bytes(b"# native entrypoint\n")
                    with self.assertRaisesRegex(ValueError, "project-owned"):
                        build(target)
                    self.assertEqual(config.read_bytes(), b"app_key = 'fixture_private_provider'\n")
                    self.assertEqual(entry.read_bytes(), b"# native entrypoint\n")

    def test_private_config_check_needs_an_exact_independent_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trusted, project = root / "trusted", root / "project"
            for folder in (trusted, project):
                folder.mkdir()
                (folder / "config.py").write_bytes(b"app_secret = 'fixture_private_value'\n")
            self.assertEqual(verify_safety(project)["status"], "failed")
            self.assertEqual(verify_safety(project, trusted, ["config.py"])["status"], "passed")
            self.assertEqual(verify_safety(project, project, ["config.py"])["status"], "failed")
            (project / "entry.py").write_bytes(b"app_secret = 'fixture_new_literal'\n")
            self.assertEqual(verify_safety(project, trusted, ["config.py"])["status"], "failed")
            (project / "config.py").write_bytes(b"app_secret = '<APP_SECRET>'\n")
            rules = verify_safety(project, trusted, ["config.py"])["findings"]
            self.assertIn("preserved_config_mismatch", [r["rule"] for r in rules])
            self.assertNotIn("fixture_", json.dumps(rules))

    def test_final_zip_rejects_stripped_swapped_or_nested_config_and_modified_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = "settings/gateway.py"
            files = {"plugin_main.py": b"# fixture", config: b"# unit A private provider"}
            for directory in ("gateway", "hbase", "fs"):
                files[directory + "/__init__.py"] = b"# fixed package"
            for name, data in files.items():
                path = root / name
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(data)
            zip_path = root / "unit.zip"

            def pack(members):
                with ZipFile(zip_path, "w") as archive:
                    for name, data in members.items():
                        archive.writestr(name, data)

            pack(files)
            self.assertEqual(verify_zip(zip_path, root, [config], root)["files_compared"], 5)
            for changes in ({config: b"<APP_KEY>"}, {config: b"# unit B private provider"},
                            {"gateway/__init__.py": b"# changed"}):
                pack({**files, **changes})
                with self.assertRaisesRegex(ValueError, "differs"):
                    verify_zip(zip_path, root, [config], root)
            for missing in ({k: v for k, v in files.items() if k != config},
                            {"operator/" + k: v for k, v in files.items()}):
                pack(missing)
                with self.assertRaisesRegex(ValueError, "missing"):
                    verify_zip(zip_path, root, [config], root)


if __name__ == "__main__":
    unittest.main()
