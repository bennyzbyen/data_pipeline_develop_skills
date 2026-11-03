"""Audit bounded offline conversion candidates against frozen document evidence.

This checks declared rule paths, not arbitrary formula equivalence. It neither
parses business prose nor promotes a fixture to an approved report contract.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json


EVIDENCE_KEYS = ("target_field", "field_name", "source_field", "source_desc",
                 "source_table", "calculation_logic", "field_type")


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def evidence_digest(field):
    evidence = {key: " ".join(str(field.get(key, "")).split()) for key in EVIDENCE_KEYS}
    return hashlib.sha256(canonical(evidence).encode("utf-8")).hexdigest()


def check_routing(contract, reference, require):
    """Match reviewed dependencies by position while allowing consistent ID renames."""
    steps = contract["steps"]
    graph = reference.get("graph")
    if graph is None:
        require(len(contract["sources"]) == 1, "linear fixture requires one source")
        source = next(iter(contract["sources"]))
        graph = [{"input": "source." + source} if index == 0 else {"input": f"step.{index - 1}"}
                 for index in range(len(steps))]
    require(isinstance(graph, list) and len(graph) == len(steps), "reviewed dependency count differs")
    identifiers = set(contract["sources"])
    dependencies, used_sources = [], set()
    for index, step in enumerate(steps):
        require(step["op"] in {"select", "project", "filter", "rename", "derive", "aggregate", "deduplicate", "join"},
                f"steps.{index} has an unsupported routing operation")
        routing = graph[index]
        require(set(routing) == ({"left", "right"} if step["op"] == "join" else {"input"}),
                f"steps.{index} has unsupported routing")
        keys = {check["path"][2] for check in reference["contract_checks"]
                if check["path"][:2] == ["steps", index] and len(check["path"]) >= 3}
        require(set(step) == keys | set(routing) | {"id"}, f"steps.{index} has unaudited properties")
        parents = set()
        for key, endpoint in routing.items():
            kind, name = endpoint.split(".", 1)
            if kind == "source":
                require(name in contract["sources"], f"steps.{index} refers to an unknown source")
                expected = name
                used_sources.add(name)
            elif kind == "step" and name.isdecimal() and int(name) < index:
                parent = int(name)
                expected = steps[parent]["id"]
                parents.add(parent)
            else:
                raise ValueError("dependency must refer to a source or an earlier step")
            require(step[key] == expected, f"steps.{index}.{key} bypasses the reviewed rule chain")
        require(isinstance(step["id"], str) and bool(step["id"]) and step["id"] not in identifiers,
                f"steps.{index} has an invalid or reused identifier")
        identifiers.add(step["id"])
        dependencies.append(parents)
    require(used_sources == set(contract["sources"]), "fixture has unbound or unused sources")
    required, pending = set(), [len(steps) - 1]
    while pending:
        index = pending.pop()
        if index not in required:
            required.add(index)
            pending.extend(dependencies[index])
    require(len(required) == len(steps), "output bypasses reviewed dependency steps")
    require(contract["outputs"]["offline_result"]["input"] == steps[-1]["id"], "output bypasses the reviewed rule chain")


def validate_conversion(fields, candidate, reference):
    """Return passed (fragment), pending (no execution), or failed; mutate nothing."""
    if not isinstance(candidate, dict) or not isinstance(reference, dict):
        return {"status": "failed", "errors": ["candidate and reference must be JSON objects"],
                "business_approved": False, "full_report_ready": False}
    errors = []
    def require(condition, message):
        if not condition:
            errors.append(message)

    try:
        allowed = {"version", "kind", "fixture_only", "candidate_origin", "document_sha256",
                   "business_approved", "full_report_ready", "bindings", "rules", "pending_ids",
                   "output_fields", "execution_contract", "source_data", "params", "pending_spec", "source_bindings"}
        require(not (set(candidate) - allowed), "candidate has undeclared keys")
        require(type(candidate.get("version")) is int and candidate["version"] == 1 and candidate.get("kind") == "document_rule_candidate"
                and candidate.get("fixture_only") is True, "candidate must be an isolated rule fixture")
        require(candidate.get("candidate_origin") == "assistant_session_candidate", "candidate origin is missing or unsupported")
        require(reference.get("business_approved") is False and reference.get("full_report_ready") is False,
                "reference must preserve pending business approval")
        require(candidate.get("business_approved") is False and candidate.get("full_report_ready") is False,
                "candidate cannot approve business rules or the full report")
        require(candidate.get("document_sha256") == reference["document_sha256"], "document evidence differs")
        by_name = {field["target_field"]: field for field in fields}
        require(len(by_name) == len(fields), "extracted evidence contains duplicate targets")
        actual = {name: evidence_digest(by_name[name]) for name in reference["evidence"]}
        require(actual == reference["evidence"], "extracted field evidence differs from frozen reference")
        bindings = candidate["bindings"]
        require(all(set(binding) == {"target_field", "evidence_sha256"} for binding in bindings), "invalid evidence binding")
        bound = {binding["target_field"]: binding["evidence_sha256"] for binding in bindings}
        require(len(bound) == len(bindings) and bound == reference["evidence"], "candidate field evidence differs")
        require(Counter(map(canonical, candidate["rules"])) == Counter(map(canonical, reference["rules"])),
                "candidate rule targets or outcomes differ")
        pending = candidate["pending_ids"]
        require(len(set(pending)) == len(pending) and set(pending) == set(reference["pending_ids"]),
                "candidate must preserve every pending dependency")
        require(candidate["output_fields"] == reference["output_fields"], "candidate output scope differs")
        require(canonical({"source_data": candidate.get("source_data", {}), "params": candidate.get("params", {})})
                == canonical(reference.get("fixture_inputs", {"source_data": {}, "params": {}})), "candidate changed frozen fixture inputs")
        if not reference["output_fields"]:
            require("execution_contract" not in candidate, "pending rules must not create an execution contract")
            require("source_bindings" not in candidate, "pending source details belong in pending_spec")
            require(canonical(candidate.get("pending_spec")) == canonical(reference["pending_spec"]), "pending formula details differ")
        else:
            require("pending_spec" not in candidate, "fragment cannot carry an unchecked pending formula")
            contract = candidate["execution_contract"]
            require(set(contract) == {"version", "sources", "steps", "outputs", "writes"}
                    and type(contract["version"]) is int and contract["version"] == 1,
                    "candidate contract must use the bounded version 1 fixture shape")
            require(bool(contract["sources"]) and set(contract["sources"]) == set(candidate["source_data"]), "fixture source inventory differs")
            if reference.get("graph") is not None:
                bindings = reference["source_bindings"]
                require(canonical(candidate.get("source_bindings")) == canonical(bindings), "candidate source evidence bindings differ")
                require(set(bindings) == set(contract["sources"]) and all(names and set(names) <= set(reference["evidence"])
                        for names in bindings.values()), "source bindings require extracted field evidence for every source")
            else:
                require("source_bindings" not in candidate, "linear fixture has unaudited source bindings")
            require(all(set(source) == {"kind", "columns"} and source["kind"] == "injected"
                        for source in contract["sources"].values()), "fixture sources must be injected columns only")
            require(set(contract["outputs"]) == {"offline_result"}
                    and set(contract["outputs"]["offline_result"]) == {"input", "columns"}, "fixture output inventory differs")
            require(contract["writes"] == {"offline_result": {"kind": "clickhouse", "mode": "append", "table": "fixture.result"}},
                    "fixture writes must be append-only fixture.result")
            assertions = reference["contract_checks"]
            step_indices = {check["path"][1] for check in assertions if check["path"][0] == "steps"}
            require(bool(step_indices) and step_indices == set(range(len(contract["steps"]))), "candidate step count differs")
            check_routing(contract, reference, require)
            for check in assertions:
                value = contract
                for key in check["path"]:
                    value = value[key]
                if "unordered_equals" in check:
                    matches = Counter(map(canonical, value)) == Counter(map(canonical, check["unordered_equals"]))
                else:
                    matches = canonical(value) == canonical(check["equals"])
                require(matches, "contract rule differs at " + ".".join(map(str, check["path"])))
    except (KeyError, TypeError, ValueError, IndexError, AttributeError, StopIteration) as exc:
        errors.append("invalid conversion data: " + type(exc).__name__)
    return {"status": "failed" if errors else ("passed" if reference.get("output_fields") else "pending"),
            "errors": errors, "evidence_fields": len(reference.get("evidence", {})),
            "rule_checks": len(reference.get("contract_checks", [])),
            "pending_ids": list(reference.get("pending_ids", [])),
            "business_approved": False, "full_report_ready": False,
            "candidate_origin": candidate.get("candidate_origin")}
