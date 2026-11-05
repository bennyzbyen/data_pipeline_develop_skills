"""Offline regressions for source-based operator refactors and private ZIP delivery."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
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
from verify_cot_manifest_semantics import validate_project
from verify_cot_runtime_semantics import import_from_path, isolated_imports, run_verification


class OperatorRefactors(unittest.TestCase):
    def test_single_mode_units_follow_declared_columns_and_source_connection(self):
        with tempfile.TemporaryDirectory() as tmp:
            for table, mode, count in [("rpt_stock", "with_period", 7), ("rpt_plain_p", "without_period", 4)]:
                with self.subTest(table=table):
                    facts = facts_for(table, ["id", "batch", "created_at", "amount"])
                    state = {"fs_root_dir": "/fixture-state/" + table, "initial_watermark": "2001-02-03 00:00:00"}
                    facts["codegen_contract"]["runtime_contract"] = state
                    row = facts["cot_report_tables"][0]
                    source_params = {"period_column": "batch", "last_update_time_column": "created_at",
                                     "code_column": "id", "key_column": "id"}
                    row.update(sync_mode=mode, source_group="fixture_store", parameters={"source_informations": source_params})
                    row["rowkey_contract"]["columns"] = ["batch", "id"] if mode == "with_period" else ["id"]
                    project = Path(tmp) / table
                    generate(facts, project)
                    self.assertEqual(validate_project(project)["status"], "passed")
                    source = json.loads((project / "params.example.json").read_text(encoding="utf-8"))["source_informations"]
                    self.assertEqual(source["last_update_time_column"], "created_at")
                    if mode == "with_period":
                        self.assertEqual((source["period_column"], source["period"], source["code_column"]), ("batch", [], "id"))
                    else:
                        self.assertNotIn("period_column", source)
                    self.assertEqual(run_verification(project)["case_count"], count)
                    with isolated_imports(project, {}), patch.dict(sys.modules, {"pymysql": types.ModuleType("pymysql")}):
                        module = import_from_path("cot_sync_" + mode + ".etl_source", project / ("cot_sync_" + mode) / "etl_source.py")
                        url, settings = module.get_mysql_url(table)
                        self.assertIn("/fixture_store?", url)
                        self.assertEqual(settings["db"], "fixture_store")
                        common = sys.modules["plugin_common"]
                        with patch.object(common, "ClientWrapper") as wrapper:
                            fs = wrapper.return_value.fs_client
                            fs.exists.return_value = False
                            self.assertEqual(common.TimeStamp_Update().fetch_last_timestamp(table), state["initial_watermark"])
                            fs.exists.assert_called_once_with(f"{state['fs_root_dir']}/last_sync_time/{table}_last_sync_time.tsv")
                        for cycle in ("B1", "B10", "B1_west", "[B]"):
                            (project / f"{cycle}_{table}_123.csv").touch()
                        self.assertEqual(common.period_csv_files(project, "B1", table), [str(project / f"B1_{table}_123.csv")])
                        self.assertEqual(common.period_csv_files(project, "[B]", table), [str(project / f"[B]_{table}_123.csv")])

    def test_wrapped_gateway_error_retains_only_current_stage_evidence(self):
        debugger = SKILLS / "data-job-log-debugger/scripts/analyze_data_job_log.py"
        log = """INFO pipeline_start table=fixture
INFO stage_complete stage=timestamp_update status=success
INFO pipeline_start table=fixture
INFO stage_skip stage=gate reason=disabled
INFO stage_complete stage=gate status=success
INFO stage_complete stage=clickhouse_write status=success
INFO stage_start stage=hbase_prepare
ERROR gateway auth failed: app key is disabled Authorization: Bearer fixture_private_value
ERROR pipeline_failed stage=hbase_prepare
Traceback (most recent call last):
  File "/runtime/plugins/fixture_20261105_010203_111111/entry.py", line 1, in run
RuntimeError: Gateway request failed: None
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "operator.log"
            path.write_text(log, encoding="utf-8")
            result = subprocess.check_output([sys.executable, str(debugger), "--log", str(path), "--format", "json"],
                                             env={**os.environ, "PYTHONUTF8": "1"}, encoding="utf-8")
            report = json.loads(result)
            self.assertEqual(report["primary_pattern_id"], "gateway_app_disabled")
            self.assertEqual(report["completed_stages"], ["clickhouse_write"])
            self.assertEqual(report["failure_stage"], "hbase_prepare")
            self.assertEqual(report["operator_packages"], ["fixture_20261105_010203_111111"])
            self.assertNotIn("fixture_private_value", result)

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
            facts["codegen_contract"]["runtime_contract"] = {"fs_root_dir": "/fixture-state/sync"}
            plan = root / "plan.json"
            plan.write_text(json.dumps(build_plan("standard_report")), encoding="utf-8")
            for name, relative, build in [
                ("sync", "cot_config/plugin_config.py", lambda path: generate(facts, path)),
                ("report", "params_configs/db_config.py", lambda path: scaffold(plan, path)),
            ]:
                with self.subTest(name=name):
                    target = root / name
                    build(target)
                    if name == "sync":
                        # Rebuild the old unmodified scaffold, which always used the project-name path.
                        manifest_path = target / "cot_sync_manifest.json"
                        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                        manifest.pop("fs_root_dir")
                        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                        config = target / relative
                        old = config.read_text(encoding="utf-8").replace('fs_root_dir = "/fixture-state/sync"',
                                                                        'fs_root_dir = "/datahub/project_storage/sync"')
                        config.write_text(old, encoding="utf-8")
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
