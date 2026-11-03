#!/usr/bin/env python3
"""Offline declared type, precision, grain, join and temporal-boundary regressions."""
from __future__ import annotations

from pipeline_test_support import SOURCE_ROOT

import copy
import csv
from datetime import date, datetime, timedelta, tzinfo
from decimal import Decimal, localcontext
import importlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

REPORT = SOURCE_ROOT / "skills/report-codegen"
sys.path.insert(0, str(REPORT / "scripts"))
from report_contract import validate_execution_contract
from scaffold_report_project import scaffold
from verify_generic_report_runtime_semantics import build_plan, purge_generated_modules


def contract(columns, source_rule=None, output_rule=None):
    return {"version": 1, "sources": {"data": dict({"kind": "injected", "columns": columns}, **(source_rule or {}))},
            "steps": [{"id": "final", "op": "project", "input": "data", "columns": columns}],
            "outputs": {"result": dict({"input": "final", "columns": columns}, **(output_rule or {}))},
            "writes": {"result": {"kind": "clickhouse", "table": "fixture.result", "mode": "append"}}}


class StaticConstraints(unittest.TestCase):
    def check(self, value):
        return validate_execution_contract(value, [{"target_name": "result", "physical_table": "fixture.result", "final_columns": value["outputs"]["result"]["columns"]}])

    def test_malformed_or_unknown_column_constraints_block_codegen(self):
        for rule in ({"column_constraints": []}, {"column_constraints": {"missing": {"nullable": False}}},
                     {"column_constraints": {"id": {"type": "guess"}}}, {"column_constraints": {"id": {"nullable": "false"}}},
                     {"column_constraints": {"id": {"type": "Int8", "min": 20, "max": 10}}},
                     {"column_constraints": {"id": {"type": "Decimal(2,3)"}}},
                     {"column_constraints": {"id": {"type": "Date", "min": "2026-02-30"}}},
                     {"column_constraints": {"id": {"type": "Date", "min": "2026-01-01", "min_from": "params.start"}}},
                     {"column_constraints": {"id": {"nullable": True, "max_inclusive": False}}},
                     {"unique_by": ["id", "id"]}, {"unique_by": ["missing"]}):
            with self.subTest(rule=rule):
                value = contract(["id"], source_rule=rule)
                before = copy.deepcopy(value)
                result = self.check(value)
                self.assertEqual("failed", result["status"], result)
                self.assertTrue(any("execution_contract.sources.data" in item["path"] for item in result["errors"]), result)
                self.assertEqual(before, value)

    def test_invalid_output_grain_and_value_rules_are_not_silently_ignored(self):
        for rule in ({"unique_by": ["missing"]}, {"column_constraints": {"missing": {"nullable": False}}}):
            self.assertEqual("failed", self.check(contract(["id"], output_rule=rule))["status"])

    def test_invalid_join_cardinality_and_deduplication_policy_are_rejected(self):
        for policy in ("unverified", True, []):
            value = contract(["id"])
            value["steps"] = [{"id": "final", "op": "join", "left": "data", "right": "data", "on": ["id"], "validate": policy}]
            self.assertEqual("failed", self.check(value)["status"])
        for policy in (None, 0, "any"):
            value = contract(["id"])
            value["steps"] = [{"id": "final", "op": "deduplicate", "input": "data", "subset": ["id"], "keep": policy}]
            self.assertEqual("failed", self.check(value)["status"])

    def test_explicit_rules_and_unknown_types_are_kept_separate(self):
        value = contract(["id", "day"], source_rule={"unique_by": ["id", "day"], "column_constraints": {
            "id": {"nullable": False}, "day": {"type": "Date", "min_from": "params.start", "max_from": "params.stop", "max_inclusive": False}}})
        self.assertEqual("passed", self.check(value)["status"])
        self.assertEqual("passed", self.check(contract(["id"]))["status"])


class RuntimeConstraints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        path = cls.root / "plan.json"
        path.write_text(json.dumps(build_plan("standard_report")), encoding="utf-8")
        cls.project = cls.root / "project"
        scaffold(path, cls.project)
        purge_generated_modules()
        sys.path.insert(0, str(cls.project))
        cls.runtime = importlib.import_module("data_utils.contract_runtime")
        cls.storage = importlib.import_module("data_utils.data_storage")

    @classmethod
    def tearDownClass(cls):
        sys.path.remove(str(cls.project))
        purge_generated_modules()
        cls.temporary.cleanup()

    def run_frame(self, frame, source_rule=None, output_rule=None, params=None):
        value = contract(list(frame.columns), source_rule, output_rule)
        return self.runtime.execute_contract({"data": frame}, {}, params or {}, value)["result"]

    def test_nonnullable_sources_and_outputs_reject_nulls(self):
        frame = pd.DataFrame({"id": ["A", None]})
        for where in ("source_rule", "output_rule"):
            with self.subTest(where=where), self.assertRaises(ValueError):
                self.run_frame(frame, **{where: {"column_constraints": {"id": {"nullable": False}}}})

    def test_unknown_nullability_and_empty_frames_preserve_existing_values(self):
        frame = pd.DataFrame({"id": ["A", None]})
        pd.testing.assert_frame_equal(frame, self.run_frame(frame))
        empty = frame.iloc[:0]
        pd.testing.assert_frame_equal(empty, self.run_frame(empty, {"column_constraints": {"id": {"nullable": False}}}))

    def test_integer_ranges_fractional_values_and_booleans_are_rejected(self):
        for type_name, bad in (("Int8", "128"), ("Int8", "-129"), ("UInt64", "-1"),
                               ("UInt64", str(2 ** 64)), ("Int64", "1.5"), ("Int64", True)):
            with self.subTest(type=type_name, bad=bad), self.assertRaises(ValueError):
                self.run_frame(pd.DataFrame({"n": [bad]}), {"column_constraints": {"n": {"type": type_name}}})

    def test_large_integers_and_exact_decimal_values_are_not_coerced(self):
        for type_name, values in (("UInt64", [str(2 ** 64 - 1), None]),
                                  ("Decimal(4,2)", ["99.99", "1.2300", "0.0000"]),
                                  ("Decimal(2,2)", [Decimal("0.99"), Decimal("-0.99"), Decimal("0.00")]),
                                  ("Decimal(76,0)", [str(10 ** 76 - 1)])):
            with self.subTest(type=type_name), localcontext() as context:
                context.prec = 6
                frame = pd.DataFrame({"n": values})
                before = frame.copy(deep=True)
                pd.testing.assert_frame_equal(before, self.run_frame(frame, {"column_constraints": {"n": {"type": type_name}}}))
                pd.testing.assert_frame_equal(before, frame)

    def test_decimal_precision_and_scale_never_round_silently(self):
        for value in ("1.234", "100.00", "1e1000000"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.run_frame(pd.DataFrame({"n": [value]}), {"column_constraints": {"n": {"type": "Decimal(4,2)"}}})

    def test_finite_float_and_string_constraints_reject_incompatible_values(self):
        for type_name, value in (("Float32", "1e40"), ("Float64", float("inf")), ("String", 42)):
            with self.subTest(type=type_name), self.assertRaises(ValueError):
                self.run_frame(pd.DataFrame({"n": [value]}), {"column_constraints": {"n": {"type": type_name}}})

    def test_numeric_bounds_are_explicitly_inclusive_or_exclusive(self):
        rule = {"column_constraints": {"n": {"type": "Int64", "min": 1, "max": 3, "max_inclusive": False}}}
        frame = pd.DataFrame({"n": [1, 2]})
        pd.testing.assert_frame_equal(frame, self.run_frame(frame, rule))
        with self.assertRaises(ValueError):
            self.run_frame(pd.DataFrame({"n": [3]}), rule)
        frame = pd.DataFrame({"n": [0, 1]})
        pd.testing.assert_frame_equal(frame, self.run_frame(frame, {"column_constraints": {"n": {"type": "UInt8", "min": -1, "max": "1.5"}}}))
        rule = {"column_constraints": {"n": {"type": "Decimal(4,2)", "max": "0.001"}}}
        frame = pd.DataFrame({"n": ["0.00"]})
        pd.testing.assert_frame_equal(frame, self.run_frame(frame, rule))
        with self.assertRaises(ValueError):
            self.run_frame(pd.DataFrame({"n": ["0.01"]}), rule)

    def test_calendar_dates_cover_leap_days_and_half_open_month_boundaries(self):
        rule = {"column_constraints": {"day": {"type": "Date", "min_from": "params.start", "max_from": "params.stop", "max_inclusive": False}}}
        params = {"start": "2024-02-01", "stop": "2024-03-01"}
        frame = pd.DataFrame({"day": ["2024-02-01", "2024-02-29"]})
        pd.testing.assert_frame_equal(frame, self.run_frame(frame, rule, params=params))
        for bad in ("2024-03-01", "2024-02-30", "2024-01-31", "2024-2-1"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.run_frame(pd.DataFrame({"day": [bad]}), rule, params=params)

    def test_temporal_bounds_fail_when_missing_inverted_or_timezone_incompatible(self):
        for params in ({}, {"start": "2026-02-01", "stop": "2026-01-01"}):
            with self.subTest(params=params), self.assertRaises(ValueError):
                self.run_frame(pd.DataFrame({"day": []}), {"column_constraints": {"day": {"type": "Date", "min_from": "params.start", "max_from": "params.stop"}}}, params=params)
        with self.assertRaises(ValueError):
            self.run_frame(pd.DataFrame({"day": ["2026-01-01T00:00:00+00:00"]}), {"column_constraints": {"day": {"type": "DateTime", "min": "2026-01-01T00:00:00"}}})

    def test_datetime_precision_and_error_messages_do_not_expose_values(self):
        secret_value = "private-row-value"
        for bad in ("2026-01-01T00:00:00.000001", secret_value):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError) as caught:
                    self.run_frame(pd.DataFrame({"day": [bad]}), {"column_constraints": {"day": {"type": "DateTime"}}})
                self.assertNotIn(bad, str(caught.exception))

    def test_native_dates_and_explicit_timezone_instants_preserve_values(self):
        frame = pd.DataFrame({"day": [date(2026, 1, 1)]})
        pd.testing.assert_frame_equal(frame, self.run_frame(frame, {"column_constraints": {"day": {"type": "Date", "min": "2026-01-01"}}}))
        frame = pd.DataFrame({"day": [pd.Timestamp("2026-01-01T08:00:00+08:00")]})
        pd.testing.assert_frame_equal(frame, self.run_frame(frame, {"column_constraints": {"day": {"type": "DateTime", "min": "2026-01-01T00:00:00Z"}}}))

    def test_half_open_filter_window_is_checked_on_projected_outputs(self):
        frame = pd.DataFrame({"day": ["2024-01-31", "2024-02-01", "2024-02-29", "2024-03-01"]})
        value = contract(["day"], output_rule={"column_constraints": {"day": {"type": "Date", "min_from": "params.start", "max_from": "params.stop", "max_inclusive": False}}})
        value["steps"] = [{"id": "final", "op": "filter", "input": "data", "conditions": [
            {"column": "day", "operator": "ge", "value_from": "params.start"}, {"column": "day", "operator": "lt", "value_from": "params.stop"}]}]
        params = {"start": "2024-02-01", "stop": "2024-03-01"}
        result = self.runtime.execute_contract({"data": frame}, {}, params, value)["result"]
        self.assertEqual(["2024-02-01", "2024-02-29"], result["day"].tolist())
        value["steps"][0]["conditions"][1]["operator"] = "le"
        with self.assertRaises(ValueError):
            self.runtime.execute_contract({"data": frame}, {}, params, value)

    def test_aware_datetime_bounds_respect_an_explicit_fold(self):
        class FoldZone(tzinfo):
            def utcoffset(self, value): return timedelta(hours=-5 if value.fold else -4)
            def dst(self, value): return timedelta(0)
        zone = FoldZone()
        rule = {"column_constraints": {"day": {"type": "DateTime", "min_from": "params.start"}}}
        params = {"start": datetime(2026, 11, 1, 1, 15, tzinfo=zone, fold=1)}
        first = pd.DataFrame({"day": pd.Series([datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=0)], dtype=object)})
        with self.assertRaises(ValueError):
            self.run_frame(first, rule, params=params)
        second = pd.DataFrame({"day": pd.Series([datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=1)], dtype=object)})
        result = self.run_frame(second, rule, params=params)
        self.assertEqual(1, result.iloc[0]["day"].fold)
        self.assertEqual(1, second.iloc[0]["day"].fold)

    def test_unique_grain_includes_null_keys_without_inventing_null_policy(self):
        frame = pd.DataFrame({"id": ["A", None], "period": [1, 1]})
        pd.testing.assert_frame_equal(frame, self.run_frame(frame, {"unique_by": ["id", "period"]}))
        bad = pd.concat([frame, frame.iloc[1:]], ignore_index=True)
        with self.assertRaises(ValueError):
            self.run_frame(bad, {"unique_by": ["id", "period"]})

    def join(self, validation=None, output_rule=None, left_unique=False, right_unique=False):
        left = pd.DataFrame({"id": ["A", "A"], "region": ["R", "R"]})
        right = pd.DataFrame({"id": ["A", "A"], "value": [1, 2]})
        if left_unique:
            left = left.iloc[:1]
        if right_unique:
            right = right.iloc[:1]
        value = contract(["id", "region", "value"], output_rule=output_rule)
        value["sources"] = {name: {"kind": "injected", "columns": list(frame.columns)} for name, frame in (("left", left), ("right", right))}
        value["steps"] = [{"id": "final", "op": "join", "left": "left", "right": "right", "on": ["id"], **({"validate": validation} if validation else {})}]
        return self.runtime.execute_contract({"left": left, "right": right}, {}, {}, value)["result"]

    def test_declared_join_cardinality_rejects_row_multiplication(self):
        for validation in ("one_to_one", "one_to_many", "many_to_one"):
            with self.subTest(validation=validation), self.assertRaises(ValueError):
                self.join(validation)

    def test_declared_many_to_many_and_undeclared_joins_remain_valid(self):
        self.assertEqual(4, len(self.join("many_to_many")))
        self.assertEqual(4, len(self.join()))

    def test_valid_join_cardinalities_preserve_allowed_rows(self):
        for validation, left_unique, right_unique, count in (("one_to_one", True, True, 1),
                ("one_to_many", True, False, 2), ("many_to_one", False, True, 2)):
            with self.subTest(validation=validation):
                self.assertEqual(count, len(self.join(validation, left_unique=left_unique, right_unique=right_unique)))

    def test_output_grain_rejects_duplicate_aggregate_dimensions(self):
        with self.assertRaises(ValueError):
            self.join(output_rule={"unique_by": ["region"]})

    def test_grouped_null_keys_and_nullable_counts_keep_existing_semantics(self):
        frame = pd.DataFrame({"region": ["R", "R", None, None], "amount": [1, None, 4, 7]})
        value = contract(["region", "amount"])
        value["steps"] = [{"id": "final", "op": "aggregate", "input": "data", "group_by": ["region"],
                           "aggregations": {"total": {"column": "amount", "agg": "sum"}, "count": {"column": "amount", "agg": "count"}}}]
        value["outputs"]["result"] = {"input": "final", "columns": ["region", "total", "count"], "unique_by": ["region"]}
        result = self.runtime.execute_contract({"data": frame}, {}, {}, value)["result"]
        self.assertEqual([1, 11], result["total"].tolist())
        self.assertEqual([1, 2], result["count"].tolist())
        self.assertTrue(pd.isna(result.iloc[1]["region"]))

    def test_deduplication_false_removes_all_duplicates_and_keeps_order(self):
        frame = pd.DataFrame({"id": ["A", "A", "B"], "n": [1, 2, 3]})
        for keep, expected in ((False, [3]), ("first", [1, 3]), ("last", [2, 3])):
            value = contract(list(frame.columns))
            value["steps"] = [{"id": "final", "op": "deduplicate", "input": "data", "subset": ["id"], "keep": keep}]
            result = self.runtime.execute_contract({"data": frame}, {}, {}, value)["result"]
            self.assertEqual(expected, result["n"].tolist())

    def test_repeated_calls_revalidate_changed_data_without_stale_cache(self):
        frame = pd.DataFrame({"n": [1]})
        rule = {"column_constraints": {"n": {"type": "Int8"}}}
        self.run_frame(frame, rule)
        frame.loc[0, "n"] = 128
        with self.assertRaises(ValueError):
            self.run_frame(frame, rule)

    def write(self, outputs, value, params=None):
        class Client:
            def __init__(self): self.events = []
            def command(self, statement): self.events.append(("command", statement))
            def insert_df(self, table, frame): self.events.append(("insert", table, frame.copy()))
        client = Client()
        with patch.object(self.storage, "execution_contract", value):
            result = self.storage.DataStorage(outputs, {}, dict(params or {}, clickhouse_client=client)).run()
        return client.events, result

    def test_integer_writer_preserves_large_values_with_nulls(self):
        for type_name, number in (("Int64", "9007199254740993"), ("UInt64", str(2 ** 64 - 1))):
            with self.subTest(type=type_name):
                value = contract(["n"])
                value["writes"]["result"].update(columns=["n"], column_types=[type_name])
                events, _ = self.write({"result": pd.DataFrame({"n": [number, None]})}, value)
                self.assertEqual([number, None], events[0][2]["n"].tolist())

    def test_native_nullable_integer_writer_preserves_extreme_values(self):
        for type_name, number in (("Int64", -(2 ** 63)), ("UInt64", 2 ** 64 - 1)):
            with self.subTest(type=type_name):
                value = contract(["n"])
                value["writes"]["result"].update(columns=["n"], column_types=[type_name])
                frame = pd.DataFrame({"n": pd.Series([number, None], dtype=type_name)})
                events, _ = self.write({"result": frame}, value)
                self.assertEqual([str(number), None], events[0][2]["n"].tolist())
                events, _ = self.write({"result": frame.iloc[:1]}, value)
                self.assertEqual([str(number)], events[0][2]["n"].tolist())

    def test_integer_writer_rejects_overflow_before_writing(self):
        value = contract(["n"])
        value["writes"]["result"].update(columns=["n"], column_types=["Int8"])
        with self.assertRaises(ValueError):
            self.write({"result": pd.DataFrame({"n": [128]})}, value)

    def test_integer_file_writer_preserves_large_values_and_null_marker(self):
        value = contract(["n"])
        value["writes"]["result"].update(columns=["n"], column_types=["Nullable(Int64)"], transport="insert_file")
        captured = []
        def insert_file(client, table, file_path, column_names, database, settings):
            captured.extend(csv.reader(io.StringIO(Path(file_path).read_text(encoding="utf-8"))))
        self.write({"result": pd.DataFrame({"n": ["9007199254740993", None]})}, value, {"clickhouse_insert_file": insert_file})
        self.assertEqual([["9007199254740993"], ["\\N"]], captured)

    def test_existing_integer_text_normalization_is_preserved(self):
        for type_name in ("Int64", "INTEGER", "INT1 UNSIGNED", "INT(11)"):
            with self.subTest(type=type_name):
                value = contract(["n"])
                value["writes"]["result"].update(columns=["n"], column_types=[type_name])
                events, _ = self.write({"result": pd.DataFrame({"n": [" 42 ", "1.0", "1e2"]})}, value)
                self.assertEqual(["42", "1", "100"], events[0][2]["n"].tolist())

    def test_existing_boolean_wire_flags_are_preserved_without_value_constraints(self):
        value = contract(["n"])
        value["writes"]["result"].update(columns=["n"], column_types=["UInt8"])
        for series in (pd.Series([True, False]), pd.Series([True, None], dtype="boolean")):
            with self.subTest(dtype=str(series.dtype)):
                events, _ = self.write({"result": pd.DataFrame({"n": series})}, value)
                expected = ["1", None] if series.isna().any() else ["1", "0"]
                self.assertEqual(expected, events[0][2]["n"].tolist())

    def test_all_declared_output_constraints_run_before_the_first_write(self):
        value = contract(["id"])
        value["outputs"] = {name: {"input": "final", "columns": ["id"], "column_constraints": {"id": {"nullable": False}}} for name in ("good", "bad")}
        value["writes"] = {name: {"kind": "clickhouse", "table": "fixture." + name, "mode": "append"} for name in value["outputs"]}
        class Client:
            def insert_df(self, *args): raise AssertionError("write occurred before all declared constraints passed")
        with patch.object(self.storage, "execution_contract", value), self.assertRaises(ValueError):
            self.storage.DataStorage({"good": pd.DataFrame({"id": ["A"]}), "bad": pd.DataFrame({"id": [None]})}, {}, {"clickhouse_client": Client()}).run()
